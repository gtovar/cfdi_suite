import { analyzeCfdiWithCurrentTsEngine } from './currentTsEngine';

async function main() {
  const chunks: Buffer[] = [];

  for await (const chunk of process.stdin) {
    chunks.push(Buffer.isBuffer(chunk) ? chunk : Buffer.from(String(chunk)));
  }

  const xml = Buffer.concat(chunks).toString('utf8');
  const result = analyzeCfdiWithCurrentTsEngine(xml);
  process.stdout.write(JSON.stringify(result));
}

main().catch((error: unknown) => {
  const message = error instanceof Error ? error.message : 'Unknown current-ts wrapper error';
  process.stderr.write(message);
  process.exitCode = 1;
});
