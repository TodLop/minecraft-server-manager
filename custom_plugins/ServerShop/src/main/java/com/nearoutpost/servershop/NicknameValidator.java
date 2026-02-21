package com.nearoutpost.servershop;

import org.bukkit.configuration.ConfigurationSection;

import java.util.Arrays;
import java.util.List;
import java.util.regex.Pattern;
import java.util.regex.PatternSyntaxException;

/**
 * Validates nicknames against configured rules.
 * Checks length, pattern, blocked words, and color codes.
 */
public class NicknameValidator {

    private final ServerShop plugin;
    private final int minLength;
    private final int maxLength;
    private final Pattern allowedPattern;
    private final List<String> blockedWords;
    private final List<String> reservedWords;
    private final boolean allowColorCodes;

    public NicknameValidator(ServerShop plugin) {
        this.plugin = plugin;
        ConfigurationSection config = plugin.getConfig().getConfigurationSection("nickname_shop");

        if (config == null) {
            // Fallback defaults if config section missing
            this.minLength = 3;
            this.maxLength = 16;
            this.allowedPattern = null;
            this.blockedWords = List.of();
            this.reservedWords = Arrays.asList("info", "set", "reset", "resetcooldown", "reload");
            this.allowColorCodes = false;
        } else {
            this.minLength = config.getInt("min_length", 3);
            this.maxLength = config.getInt("max_length", 16);
            this.allowColorCodes = config.getBoolean("allow_color_codes", false);
            this.blockedWords = config.getStringList("blocked_words");
            List<String> configReserved = config.getStringList("reserved_words");
            this.reservedWords = configReserved.isEmpty()
                    ? Arrays.asList("info", "set", "reset", "resetcooldown", "reload")
                    : configReserved;
            this.allowedPattern = compilePattern(config.getString("allowed_pattern"));
        }
    }

    private Pattern compilePattern(String patternString) {
        if (patternString != null && !patternString.trim().isEmpty()) {
            try {
                return Pattern.compile(patternString);
            } catch (PatternSyntaxException e) {
                plugin.getLogger().warning("Invalid nickname pattern in config: " + e.getMessage());
                return null;
            }
        }
        return null;
    }

    /**
     * Validate a nickname against all configured rules.
     *
     * @param nickname The nickname to validate
     * @return ValidationResult containing success status and error message key
     */
    public ValidationResult validate(String nickname) {
        if (nickname == null || nickname.isEmpty()) {
            return ValidationResult.error("nickname-too-short");
        }

        // Check reserved words (command keywords)
        for (String reserved : reservedWords) {
            if (nickname.equalsIgnoreCase(reserved)) {
                return ValidationResult.error("nickname-reserved-word");
            }
        }

        // Check for color codes if not allowed
        if (!allowColorCodes && containsColorCodes(nickname)) {
            return ValidationResult.error("nickname-color-codes-not-allowed");
        }

        // Strip color codes for validation (length/pattern checks on display text)
        String strippedNickname = stripColorCodes(nickname);

        // Check minimum length
        if (strippedNickname.length() < minLength) {
            return ValidationResult.error("nickname-too-short");
        }

        // Check maximum length
        if (strippedNickname.length() > maxLength) {
            return ValidationResult.error("nickname-too-long");
        }

        // Check allowed pattern
        if (allowedPattern != null && !allowedPattern.matcher(strippedNickname).matches()) {
            return ValidationResult.error("nickname-invalid-characters");
        }

        // Check blocked words (case-insensitive substring match)
        for (String blockedWord : blockedWords) {
            if (strippedNickname.toLowerCase().contains(blockedWord.toLowerCase())) {
                return ValidationResult.error("nickname-blocked-word");
            }
        }

        return ValidationResult.success();
    }

    /**
     * Check if a string contains Minecraft color codes (&a, &b, etc.).
     *
     * @param text Text to check
     * @return true if color codes found
     */
    private boolean containsColorCodes(String text) {
        return text.matches(".*&[0-9a-fk-or].*");
    }

    /**
     * Strip Minecraft color codes from a string.
     *
     * @param text Text to strip
     * @return Text without color codes
     */
    private String stripColorCodes(String text) {
        return text.replaceAll("&[0-9a-fk-or]", "");
    }

    /**
     * Result of nickname validation.
     */
    public static class ValidationResult {
        private final boolean valid;
        private final String errorMessageKey;

        private ValidationResult(boolean valid, String errorMessageKey) {
            this.valid = valid;
            this.errorMessageKey = errorMessageKey;
        }

        public static ValidationResult success() {
            return new ValidationResult(true, null);
        }

        public static ValidationResult error(String messageKey) {
            return new ValidationResult(false, messageKey);
        }

        public boolean isValid() {
            return valid;
        }

        public String getErrorMessageKey() {
            return errorMessageKey;
        }
    }

    // Getters for config values (used in messages)
    public int getMinLength() {
        return minLength;
    }

    public int getMaxLength() {
        return maxLength;
    }
}
