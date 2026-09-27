import { Client, TextChannel } from "discord.js";
import { resolveReplyTarget } from "./replyThread.js";
import { log } from "./log.js";

const DISCORD_MESSAGE_LIMIT = 2000;

export interface EditableMessage {
  readonly authorId: string;
  readonly content: string;
}

/**
 * Why an edit must not happen, or null when it may. Only the bot's own
 * messages are editable — rewriting somebody else's words is never a
 * correction, and Discord would refuse it anyway, but only after login.
 */
export function editRefusal(message: EditableMessage, botUserId: string, next: string): string | null {
  if (message.authorId !== botUserId) {
    return "That message was not posted by this bot; only the bot's own messages can be edited.";
  }
  if (message.content === next) {
    return "The new text is identical to the current one; nothing to edit.";
  }
  if (next.length > DISCORD_MESSAGE_LIMIT) {
    return `The new text has ${next.length} characters; Discord allows ${DISCORD_MESSAGE_LIMIT}.`;
  }
  return null;
}

/**
 * Replace the text of one of the bot's own messages in a text channel.
 *
 * A dry run logs in, fetches the message and prints the current and the new
 * text side by side, then returns before `edit()`. Discord marks the message
 * "(edited)" but sends no new notification — say so when the reader needs to
 * know about the change.
 */
export async function runEdit(
  client: Client,
  token: string,
  guildId: string,
  channelQuery: string,
  messageId: string,
  next: string,
  dryRun: boolean,
): Promise<void> {
  return new Promise<void>((resolve, reject) => {
    client.once("clientReady", async () => {
      try {
        const guild = await client.guilds.fetch(guildId);
        await guild.channels.fetch();
        const texts = [...guild.channels.cache.values()].filter(
          (c): c is TextChannel => c instanceof TextChannel,
        );
        const channel = resolveReplyTarget([], texts, channelQuery);
        if (!channel) {
          log(`No text channel matches "${channelQuery}". Run \`npm run read\` to list channels.`);
          process.exitCode = 1;
          return;
        }

        const message = await channel.messages.fetch(messageId);
        const refusal = editRefusal(
          { authorId: message.author.id, content: message.content },
          client.user?.id ?? "",
          next,
        );
        if (refusal) {
          log(`Refused: ${refusal}`);
          process.exitCode = 1;
          return;
        }

        if (dryRun) {
          log(`[dry-run] would edit ${message.url}`);
          log(`[dry-run] --- current ---\n${message.content}`);
          log(`[dry-run] --- new ---\n${next}`);
          return;
        }

        await message.edit(next);
        log(`Edited ${message.url}`);
      } catch (err) {
        log(`ERROR: ${err instanceof Error ? err.message : String(err)}`);
        process.exitCode = 1;
      } finally {
        await client.destroy();
        resolve();
      }
    });

    client.login(token).catch((err: unknown) => {
      reject(err instanceof Error ? err : new Error(String(err)));
    });
  });
}
