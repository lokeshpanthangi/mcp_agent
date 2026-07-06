import { McpCommand, listMcpCommands } from "../api";

/** True while the user is still typing a slash-command (not yet on trailing args). */
export function slashQuery(input: string, commands: McpCommand[]): string | null {
  if (!input.startsWith("/")) return null;

  const body = input.slice(1);
  for (const cmd of commands) {
    const cmdBody = cmd.slash.slice(1);
    const lower = body.toLowerCase();
    const cmdLower = cmdBody.toLowerCase();
    if (lower === cmdLower || lower.startsWith(`${cmdLower} `)) {
      return null;
    }
  }
  return body.toLowerCase();
}

export function filterCommands(commands: McpCommand[], query: string): McpCommand[] {
  const q = query.toLowerCase();
  if (!q) return commands;
  return commands.filter((cmd) => {
    const haystack = `${cmd.slash} ${cmd.usage} ${cmd.name} ${cmd.server} ${cmd.description}`.toLowerCase();
    return haystack.includes(q);
  });
}

/** Client-side guard before sending an incomplete slash-command. */
export function missingPromptArgs(input: string, commands: McpCommand[]): string | null {
  const trimmed = input.trim();
  for (const cmd of commands) {
    if (!trimmed.toLowerCase().startsWith(cmd.slash.toLowerCase())) continue;
    const trailing = trimmed.slice(cmd.slash.length).trim();
    const required = cmd.arguments.filter((a) => a.required);
    if (required.length > 0 && !trailing) {
      return cmd.usage
        ? `Add the required value: ${cmd.usage}`
        : `${cmd.slash} requires ${required.map((a) => a.name).join(", ")}`;
    }
    return null;
  }
  return null;
}

export async function loadMcpCommands(): Promise<McpCommand[]> {
  try {
    return await listMcpCommands();
  } catch {
    return [];
  }
}
