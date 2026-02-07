package dev.hjjang.coraspectator;

import org.bukkit.command.Command;
import org.bukkit.command.CommandExecutor;
import org.bukkit.command.CommandSender;

public class RCONCommandHandler implements CommandExecutor {
    private final SpectatorManager spectatorManager;

    public RCONCommandHandler(SpectatorManager spectatorManager) {
        this.spectatorManager = spectatorManager;
    }

    @Override
    public boolean onCommand(CommandSender sender, Command cmd, String label, String[] args) {
        if (!cmd.getName().equalsIgnoreCase("cora-spectate")) {
            return false;
        }

        if (args.length == 0) {
            sender.sendMessage("ERROR: Missing subcommand. Use: start, end, or status");
            return false;
        }

        String subCommand = args[0].toLowerCase();

        switch (subCommand) {
            case "start":
                if (args.length != 4) {
                    sender.sendMessage("ERROR: Usage: /cora-spectate start <staff> <target> <duration_seconds>");
                    return false;
                }

                String staff = args[1];
                String target = args[2];
                int duration;

                try {
                    duration = Integer.parseInt(args[3]);
                } catch (NumberFormatException e) {
                    sender.sendMessage("ERROR: Duration must be a valid number");
                    return false;
                }

                if (duration <= 0) {
                    sender.sendMessage("ERROR: Duration must be greater than 0");
                    return false;
                }

                String startResult = spectatorManager.startSession(staff, target, duration);
                sender.sendMessage(startResult);
                return true;

            case "end":
                if (args.length != 2) {
                    sender.sendMessage("ERROR: Usage: /cora-spectate end <staff>");
                    return false;
                }

                String staffToEnd = args[1];
                String endResult = spectatorManager.endSession(staffToEnd);
                sender.sendMessage(endResult);
                return true;

            case "status":
                if (args.length != 1) {
                    sender.sendMessage("ERROR: Usage: /cora-spectate status");
                    return false;
                }

                String status = spectatorManager.getStatus();
                sender.sendMessage(status);
                return true;

            default:
                sender.sendMessage("ERROR: Unknown subcommand '" + subCommand + "'. Use: start, end, or status");
                return false;
        }
    }
}
