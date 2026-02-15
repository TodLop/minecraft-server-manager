# app/services/minecraft_updater.py
"""
Minecraft Server Plugin Update Automation Service

Handles version checking, downloading, and updating for:
- Paper Server (PaperMC API)
- Modrinth Plugins (GrimAC, ViaVersion, Geyser, LuckPerms, etc.)
"""

import json
import hashlib
import shutil
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional
from dataclasses import dataclass, asdict

import httpx

from app.core.config import MINECRAFT_SERVER_PATH

# Configuration (paths derived from central config)
PLUGINS_PATH = MINECRAFT_SERVER_PATH / "plugins"
BACKUPS_PATH = MINECRAFT_SERVER_PATH / "backups"
UPDATE_LOGS_PATH = MINECRAFT_SERVER_PATH / "update_logs"
VERSIONS_FILE = MINECRAFT_SERVER_PATH / "versions.json"

# API Endpoints
PAPERMC_API_V3 = "https://fill.papermc.io/v3"
PAPERMC_DATA = "https://fill-data.papermc.io/v1"
MODRINTH_API = "https://api.modrinth.com/v2"

# HTTP client settings
TIMEOUT = 30.0
USER_AGENT = "MinecraftServerManager-Updater/1.0"


@dataclass
class VersionInfo:
    """Represents version information for a plugin"""
    version: str
    build: Optional[int] = None
    download_url: Optional[str] = None
    filename: Optional[str] = None
    sha256: Optional[str] = None
    sha512: Optional[str] = None
    changelog: Optional[str] = None
    game_versions: Optional[list] = None
    full_version: Optional[str] = None


@dataclass
class UpdateCheck:
    """Result of checking for updates"""
    plugin_id: str
    source: str
    current_version: str
    latest_version: str
    has_update: bool
    download_url: Optional[str] = None
    filename: Optional[str] = None
    sha256: Optional[str] = None
    sha512: Optional[str] = None
    changelog: Optional[str] = None
    current_full_version: Optional[str] = None
    latest_full_version: Optional[str] = None


@dataclass
class OperationLog:
    """Structured operation log entry"""
    timestamp: str
    plugin: str
    operation: str
    from_version: Optional[str] = None
    to_version: Optional[str] = None
    steps: list = None
    status: str = "pending"
    error: Optional[str] = None

    def __post_init__(self):
        if self.steps is None:
            self.steps = []

    def add_step(self, action: str, **details):
        self.steps.append({
            "time": datetime.now().strftime("%H:%M:%S"),
            "action": action,
            **details
        })

    def save(self):
        """Save log to file"""
        UPDATE_LOGS_PATH.mkdir(parents=True, exist_ok=True)
        date_str = datetime.now().strftime("%Y-%m-%d")
        filename = f"{date_str}_{self.plugin}_{self.operation}.json"
        filepath = UPDATE_LOGS_PATH / filename

        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(asdict(self), f, indent=2, ensure_ascii=False)

        return filepath


def load_versions() -> dict:
    """Load current version tracking data with auto-migration for full_version field"""
    if VERSIONS_FILE.exists():
        with open(VERSIONS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)

        # Auto-migration: Add full_version to existing entries
        plugins = data.get("plugins", {})
        migrated = False
        for plugin_id, plugin_config in plugins.items():
            if "full_version" not in plugin_config and "file" in plugin_config:
                # Extract full_version from filename
                filename = plugin_config["file"]
                full_ver = extract_version_from_filename(filename)
                if full_ver:
                    plugin_config["full_version"] = full_ver
                    migrated = True

        # Save if we migrated any entries
        if migrated:
            save_versions(data)

        return data

    return {"plugins": {}, "pending_updates": []}


def save_versions(data: dict):
    """Save version tracking data"""
    with open(VERSIONS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


async def get_papermc_latest(minecraft_version: str = "1.21.11") -> VersionInfo:
    """
    Fetch latest Paper build from PaperMC v3 API (Fill system)

    API: GET /v3/projects/paper/versions/{version}/builds
    Note: v3 API returns builds sorted newest-first (index 0 = latest)
    """
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        # Get list of builds for version (v3 API)
        url = f"{PAPERMC_API_V3}/projects/paper/versions/{minecraft_version}/builds"
        response = await client.get(url, headers={"User-Agent": USER_AGENT})
        response.raise_for_status()

        builds = response.json()  # v3 returns array directly, not {"builds": [...]}

        if not builds:
            raise ValueError(f"No builds found for Paper {minecraft_version}")

        # v3 API: Latest build is FIRST in array (index 0)
        latest = builds[0]
        build_number = latest["id"]  # v3 uses "id" instead of "build"

        # Get download info (v3 structure)
        downloads = latest.get("downloads", {})
        server_download = downloads.get("server:default", {})
        filename = server_download.get("name", f"paper-{minecraft_version}-{build_number}.jar")
        checksums = server_download.get("checksums", {})
        sha256 = checksums.get("sha256")

        # v3 uses fill-data.papermc.io for downloads
        download_url = server_download.get("url")
        if not download_url:
            # Fallback: construct URL from sha256
            download_url = f"{PAPERMC_DATA}/objects/{sha256}/{filename}"

        # Get changelog from commits
        commits = latest.get("commits", [])
        changelog = "\n".join([f"- {c.get('message', '').strip()}" for c in commits[:5]]) if commits else None

        return VersionInfo(
            version=f"{minecraft_version}-{build_number}",
            build=build_number,
            download_url=download_url,
            filename=filename,
            sha256=sha256,
            changelog=changelog,
            game_versions=[minecraft_version]
        )


async def get_modrinth_latest(
    project_id: str,
    minecraft_version: str = "1.21.11",
    loader: str = "paper",
    release_only: bool = True
) -> VersionInfo:
    """
    Fetch latest STABLE version from Modrinth API

    API: GET /v2/project/{id}/version

    Args:
        project_id: Modrinth project slug
        minecraft_version: Target MC version
        loader: Server loader (paper, bukkit, spigot, folia)
        release_only: If True, prefer stable releases but accept beta if no release exists

    Strategy:
    1. For each loader (paper, bukkit, spigot), find releases first, then betas
    2. Prefer release > beta for each loader before moving to next loader
    3. This ensures we get correct loader file even if only betas exist
    """
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        url = f"{MODRINTH_API}/project/{project_id}/version"

        # Loaders to try in order of preference for Paper servers
        loaders_to_try = ["paper", "bukkit", "spigot", "folia"] if loader == "paper" else [loader]

        best_version = None

        for try_loader in loaders_to_try:
            # Try with game version filter first
            params = {
                "game_versions": f'["{minecraft_version}"]',
                "loaders": f'["{try_loader}"]'
            }

            response = await client.get(url, params=params, headers={"User-Agent": USER_AGENT})
            response.raise_for_status()
            versions = response.json()

            # If no results with game version, try loader only
            if not versions:
                params = {"loaders": f'["{try_loader}"]'}
                response = await client.get(url, params=params, headers={"User-Agent": USER_AGENT})
                response.raise_for_status()
                versions = response.json()

            if not versions:
                continue

            # Prefer release, but accept beta for this loader
            releases = [v for v in versions if v.get("version_type") == "release"]
            betas = [v for v in versions if v.get("version_type") in ("beta", "alpha")]

            if releases:
                best_version = releases[0]
                break  # Found a release for this loader, use it
            elif betas and not best_version:
                # No release, but found beta - remember it but keep trying other loaders for releases
                best_version = betas[0]
                # Don't break - see if another loader has a release

        # If we found nothing, try without any loader filter as last resort
        if not best_version:
            response = await client.get(url, headers={"User-Agent": USER_AGENT})
            response.raise_for_status()
            versions = response.json()

            if versions:
                releases = [v for v in versions if v.get("version_type") == "release"]
                if releases:
                    best_version = releases[0]
                else:
                    best_version = versions[0]
                    print(f"[Warning] No stable releases found for {project_id}, using latest available")

        if not best_version:
            raise ValueError(f"No versions found for {project_id}")

        # Get primary file
        files = best_version.get("files", [])
        primary_file = next((f for f in files if f.get("primary")), files[0] if files else None)

        if not primary_file:
            raise ValueError(f"No download file found for {project_id}")

        hashes = primary_file.get("hashes", {})

        # Extract full version from filename (includes commit hash if present)
        filename = primary_file.get("filename")
        full_version = extract_version_from_filename(filename) if filename else None

        return VersionInfo(
            version=best_version.get("version_number"),
            download_url=primary_file.get("url"),
            filename=filename,
            sha256=hashes.get("sha256"),
            sha512=hashes.get("sha512"),
            changelog=best_version.get("changelog"),
            game_versions=best_version.get("game_versions", []),
            full_version=full_version
        )


def normalize_version(version_str: str) -> str:
    """
    Normalize version string by removing:
    - Git commit hashes (e.g., -b7a719d)
    - Build suffixes (e.g., -SNAPSHOT, -beta, -bukkit)
    - Leading 'v' prefix
    """
    import re

    v = version_str.strip()

    # Remove leading 'v' (e.g., v5.5.17 -> 5.5.17)
    if v.startswith('v'):
        v = v[1:]

    # Remove platform suffixes like -bukkit, -neoforge, -paper
    v = re.sub(r'-(bukkit|spigot|paper|neoforge|fabric|folia)$', '', v, flags=re.IGNORECASE)

    # Remove git commit hash suffix (e.g., -b7a719d, -abc1234)
    v = re.sub(r'-[a-f0-9]{6,}$', '', v, flags=re.IGNORECASE)

    # Remove SNAPSHOT/beta/alpha suffixes
    v = re.sub(r'-(SNAPSHOT|beta|alpha|rc\d*).*$', '', v, flags=re.IGNORECASE)

    return v


def parse_version_number(version_str: str) -> tuple:
    """Parse version string into comparable tuple of integers"""
    import re

    # Normalize first
    v = normalize_version(version_str)

    # Extract numeric parts (e.g., "2.3.73" -> (2, 3, 73))
    parts = re.findall(r'\d+', v)
    return tuple(int(p) for p in parts) if parts else (0,)


def extract_version_from_filename(filename: str) -> Optional[str]:
    """
    Extract full version string from JAR filename.

    Examples:
        grimac-bukkit-2.3.73-cd86c14.jar → 2.3.73-cd86c14
        ViaVersion-5.1.1.jar → 5.1.1
        paper-1.21.11-123.jar → 1.21.11-123

    Returns:
        Full version string with commit hash if present, or None if unable to parse
    """
    import re

    # Remove .jar extension
    name = filename.replace('.jar', '')

    # Pattern to match version strings with optional commit hash
    # Matches: X.Y.Z or X.Y.Z-hash or X.Y.Z-text-hash
    pattern = r'(\d+\.\d+(?:\.\d+)?(?:-[a-zA-Z0-9]+(?:-[a-f0-9]{6,})?)?)$'

    match = re.search(pattern, name)
    if match:
        return match.group(1)

    # Fallback: try to find any version-like pattern
    pattern2 = r'(\d+\.\d+(?:\.\d+)?(?:-[a-zA-Z0-9\-]+)?)$'
    match = re.search(pattern2, name)
    if match:
        return match.group(1)

    return None


def is_newer_version(
    current: str,
    latest: str,
    current_full: Optional[str] = None,
    latest_full: Optional[str] = None,
    current_filename: Optional[str] = None,
    latest_filename: Optional[str] = None
) -> bool:
    """
    Compare two version strings using three-tier comparison:
    1. Compare normalized versions (semantic: 2.3.72 < 2.3.73)
    2. If equal, compare full versions (commit hash: cd86c14 ≠ b7a719d → update available)
    3. If still equal, compare filenames (safest fallback)

    Returns True if latest is strictly newer than current.
    """
    try:
        # Tier 1: Normalize both versions for semantic comparison
        current_norm = normalize_version(current)
        latest_norm = normalize_version(latest)

        # If normalized versions differ, use semantic comparison
        if current_norm != latest_norm:
            current_parts = parse_version_number(current)
            latest_parts = parse_version_number(latest)

            # Pad shorter tuple with zeros for comparison
            max_len = max(len(current_parts), len(latest_parts))
            current_padded = current_parts + (0,) * (max_len - len(current_parts))
            latest_padded = latest_parts + (0,) * (max_len - len(latest_parts))

            return latest_padded > current_padded

        # Tier 2: Normalized versions equal, compare full versions (for commit hash changes)
        if current_full and latest_full:
            if current_full != latest_full:
                return True  # Full versions differ → update available

        # Tier 3: Full versions equal or not available, compare filenames
        if current_filename and latest_filename:
            if current_filename != latest_filename:
                return True  # Filenames differ → update available

        # Everything matches, no update
        return False

    except Exception:
        # Fallback: if parsing fails, compare normalized strings
        return normalize_version(latest) != normalize_version(current)


async def check_plugin_update(plugin_id: str, plugin_config: dict, minecraft_version: str) -> UpdateCheck:
    """Check if a specific plugin has an update available"""
    source = plugin_config.get("source")
    current_version = plugin_config.get("current_version", "0")
    current_full_version = plugin_config.get("full_version")
    current_filename = plugin_config.get("file")
    project_id = plugin_config.get("project_id", plugin_id)

    # Skip manual plugins (not trackable via API)
    if source == "manual":
        return UpdateCheck(
            plugin_id=plugin_id,
            source=source,
            current_version=current_version,
            latest_version="Manual update required",
            has_update=False,
            current_full_version=current_full_version
        )

    try:
        if source == "papermc":
            latest = await get_papermc_latest(minecraft_version)
        elif source == "modrinth":
            latest = await get_modrinth_latest(project_id, minecraft_version)
        else:
            raise ValueError(f"Unknown source: {source}")

        # For Paper, compare build numbers
        if source == "papermc":
            current_build = plugin_config.get("current_build", 0)
            has_update = latest.build > current_build
        else:
            # Use enhanced version comparison with full version and filename
            has_update = is_newer_version(
                current_version,
                latest.version,
                current_full=current_full_version,
                latest_full=latest.full_version,
                current_filename=current_filename,
                latest_filename=latest.filename
            )

        return UpdateCheck(
            plugin_id=plugin_id,
            source=source,
            current_version=current_version,
            latest_version=latest.version,
            has_update=has_update,
            download_url=latest.download_url,
            filename=latest.filename,
            sha256=latest.sha256,
            sha512=latest.sha512,
            changelog=latest.changelog,
            current_full_version=current_full_version,
            latest_full_version=latest.full_version
        )

    except Exception as e:
        return UpdateCheck(
            plugin_id=plugin_id,
            source=source,
            current_version=current_version,
            latest_version=f"Error: {str(e)}",
            has_update=False,
            current_full_version=current_full_version
        )


async def check_all_updates() -> list[UpdateCheck]:
    """Check all tracked plugins for updates"""
    versions_data = load_versions()
    minecraft_version = versions_data.get("minecraft_version", "1.21.11")
    plugins = versions_data.get("plugins", {})

    results = []
    for plugin_id, config in plugins.items():
        result = await check_plugin_update(plugin_id, config, minecraft_version)
        results.append(result)

    # Update last check time
    versions_data["last_check"] = datetime.now().isoformat()
    save_versions(versions_data)

    return results


def backup_plugin(plugin_id: str, filename: str) -> Path:
    """Create backup of current plugin JAR"""
    BACKUPS_PATH.mkdir(parents=True, exist_ok=True)

    # Determine source path (Paper is in root, plugins are in plugins/)
    if plugin_id == "paper":
        source = MINECRAFT_SERVER_PATH / filename
    else:
        source = PLUGINS_PATH / filename

    if not source.exists():
        raise FileNotFoundError(f"Plugin file not found: {source}")

    # Create timestamped backup
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_name = f"{filename}.{timestamp}.bak"
    backup_path = BACKUPS_PATH / backup_name

    shutil.copy2(source, backup_path)

    # Clean up old backups for this file
    _cleanup_old_backups(filename, keep=5)

    return backup_path


def _cleanup_old_backups(original_filename: str, keep: int = 5) -> None:
    """
    Delete old backup files, keeping only the most recent N versions.

    For versioned files (Paper, plugins), groups all versions together.
    Examples:
        - paper-1.21.11-100.jar → matches all paper-*.jar.*.bak
        - grimac-bukkit-2.3.73-cd86c14.jar → matches all grimac-bukkit-*.jar.*.bak
        - Geyser-Spigot.jar → matches Geyser-Spigot.jar.*.bak (exact)

    Args:
        original_filename: Original JAR filename (e.g., "paper-1.21.11-110.jar")
        keep: Number of recent backups to preserve per file pattern
    """
    import re

    # Normalize filename to base pattern for grouping
    # paper-1.21.11-100.jar → paper-*.jar
    # grimac-bukkit-2.3.73-cd86c14.jar → grimac-bukkit-*.jar
    # Geyser-Spigot.jar → Geyser-Spigot.jar (no version, keep exact)

    # Remove .jar extension for processing
    base = original_filename.replace('.jar', '')

    # Try to identify versioned pattern (contains digits)
    if re.search(r'-?\d+\.\d+', base):
        # Has version numbers - extract base name before version
        # paper-1.21.11-100 → paper
        # grimac-bukkit-2.3.73-cd86c14 → grimac-bukkit
        # ViaVersion-5.7.0 → ViaVersion
        parts = re.split(r'-\d+\.\d+', base, maxsplit=1)
        if parts and parts[0]:
            backup_pattern = f"{parts[0]}-*.jar.*.bak"
        else:
            # Fallback to exact match
            backup_pattern = f"{original_filename}.*.bak"
    else:
        # No version pattern detected, use exact match
        backup_pattern = f"{original_filename}.*.bak"

    # Find all backups matching this pattern
    backup_files = sorted(
        BACKUPS_PATH.glob(backup_pattern),
        key=lambda p: p.stat().st_mtime,
        reverse=True  # Newest first
    )

    # Delete old backups beyond retention limit
    files_to_delete = backup_files[keep:]
    if files_to_delete:
        logging.info(f"Cleaning up {len(files_to_delete)} old backups for pattern: {backup_pattern}")

    for backup_file in files_to_delete:
        try:
            backup_file.unlink()
            logging.info(f"Deleted old backup: {backup_file.name}")
        except Exception as e:
            logging.warning(f"Failed to delete backup {backup_file.name}: {e}")


def verify_hash(filepath: Path, expected_sha256: str = None, expected_sha512: str = None) -> bool:
    """Verify file hash matches expected value"""
    with open(filepath, "rb") as f:
        content = f.read()

    if expected_sha256:
        actual = hashlib.sha256(content).hexdigest()
        return actual.lower() == expected_sha256.lower()

    if expected_sha512:
        actual = hashlib.sha512(content).hexdigest()
        return actual.lower() == expected_sha512.lower()

    # No hash to verify
    return True


async def download_update(update: UpdateCheck) -> Path:
    """Download plugin update to temp location"""
    if not update.download_url:
        raise ValueError("No download URL available")

    async with httpx.AsyncClient(timeout=60.0, follow_redirects=True) as client:
        response = await client.get(
            update.download_url,
            headers={"User-Agent": USER_AGENT}
        )
        response.raise_for_status()

        # Save to backups folder temporarily
        temp_path = BACKUPS_PATH / f"download_{update.filename}"

        with open(temp_path, "wb") as f:
            f.write(response.content)

        # Verify hash
        if not verify_hash(temp_path, update.sha256, update.sha512):
            temp_path.unlink()
            raise ValueError("Hash verification failed")

        return temp_path


async def apply_update(plugin_id: str, update: UpdateCheck) -> OperationLog:
    """
    Apply a plugin update with full logging

    Steps:
    1. Create backup of current version
    2. Download new version
    3. Verify hash
    4. Replace file
    5. Update versions.json
    """
    log = OperationLog(
        timestamp=datetime.now().isoformat(),
        plugin=plugin_id,
        operation="update",
        from_version=update.current_version,
        to_version=update.latest_version
    )

    versions_data = load_versions()
    plugin_config = versions_data.get("plugins", {}).get(plugin_id, {})
    current_file = plugin_config.get("file")

    try:
        # Step 1: Backup
        log.add_step("backup_started", file=current_file)
        backup_path = backup_plugin(plugin_id, current_file)
        log.add_step("backup_created", path=str(backup_path))

        # Step 2: Download
        log.add_step("download_started", url=update.download_url)
        temp_file = await download_update(update)
        file_size = temp_file.stat().st_size
        log.add_step("download_complete", size=f"{file_size / 1024 / 1024:.2f}MB")

        # Step 3: Verify (already done in download_update)
        log.add_step("hash_verified", sha256=update.sha256 or "N/A", sha512=update.sha512 or "N/A")

        # Step 4: Replace file
        if plugin_id == "paper":
            dest_path = MINECRAFT_SERVER_PATH / update.filename
            # Also remove old JAR
            old_jar = MINECRAFT_SERVER_PATH / current_file
            if old_jar.exists() and old_jar != dest_path:
                old_jar.unlink()
        else:
            dest_path = PLUGINS_PATH / update.filename
            # Remove old JAR if different name
            old_jar = PLUGINS_PATH / current_file
            if old_jar.exists() and old_jar != dest_path:
                old_jar.unlink()

        shutil.move(str(temp_file), str(dest_path))
        log.add_step("file_replaced", path=str(dest_path))

        # Step 4.5: For Paper, update start.sh
        if plugin_id == "paper":
            from app.services.minecraft_server import update_start_script
            if update_start_script(update.filename):
                log.add_step("start_script_updated", new_jar=update.filename)
            else:
                log.add_step("start_script_update_failed", new_jar=update.filename)

        # Step 5: Update versions.json
        plugin_config["current_version"] = update.latest_version
        plugin_config["file"] = update.filename
        plugin_config["installed_at"] = datetime.now().isoformat()
        if update.sha256:
            plugin_config["sha256"] = update.sha256
        if update.sha512:
            plugin_config["sha512"] = update.sha512
        if plugin_id == "paper" and "-" in update.latest_version:
            plugin_config["current_build"] = int(update.latest_version.split("-")[-1])

        # Save full_version (extract from filename if not provided by update)
        if update.latest_full_version:
            plugin_config["full_version"] = update.latest_full_version
        elif update.filename:
            full_ver = extract_version_from_filename(update.filename)
            if full_ver:
                plugin_config["full_version"] = full_ver

        versions_data["plugins"][plugin_id] = plugin_config
        save_versions(versions_data)
        log.add_step("versions_updated")

        log.status = "success"

    except Exception as e:
        log.status = "failed"
        log.error = str(e)
        log.add_step("error", message=str(e))

    log.save()
    return log


def get_update_logs(limit: int = 20) -> list[dict]:
    """Get recent update operation logs"""
    logs = []

    if not UPDATE_LOGS_PATH.exists():
        return logs

    # Get all log files sorted by modification time
    log_files = sorted(
        UPDATE_LOGS_PATH.glob("*.json"),
        key=lambda f: f.stat().st_mtime,
        reverse=True
    )[:limit]

    for filepath in log_files:
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                logs.append(json.load(f))
        except:
            pass

    return logs


def get_server_status() -> dict:
    """Get basic server status information"""
    status = {
        "server_path": str(MINECRAFT_SERVER_PATH),
        "exists": MINECRAFT_SERVER_PATH.exists(),
        "plugins_count": 0,
        "jar_files": []
    }

    if PLUGINS_PATH.exists():
        jar_files = list(PLUGINS_PATH.glob("*.jar"))
        status["plugins_count"] = len(jar_files)
        status["jar_files"] = [f.name for f in jar_files]

    # Check for Paper JAR
    paper_jars = list(MINECRAFT_SERVER_PATH.glob("paper-*.jar"))
    if paper_jars:
        status["paper_jar"] = paper_jars[0].name

    return status
