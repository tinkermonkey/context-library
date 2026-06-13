import type { DiffLine } from '@tinkermonkey/heimdall-ui';

const MAX_LINES = 500;

export function computeLineDiff(fromContent: string, toContent: string): DiffLine[] {
  const a = fromContent.split('\n').slice(0, MAX_LINES);
  const b = toContent.split('\n').slice(0, MAX_LINES);
  const m = a.length;
  const n = b.length;

  const dp = Array.from({ length: m + 1 }, () => new Array(n + 1).fill(0) as number[]);
  for (let i = 1; i <= m; i++) {
    for (let j = 1; j <= n; j++) {
      dp[i][j] = a[i - 1] === b[j - 1]
        ? dp[i - 1][j - 1] + 1
        : Math.max(dp[i - 1][j], dp[i][j - 1]);
    }
  }

  const ops: Array<{ type: 'context' | 'added' | 'removed'; content: string }> = [];
  let i = m, j = n;
  while (i > 0 || j > 0) {
    if (i > 0 && j > 0 && a[i - 1] === b[j - 1]) {
      ops.unshift({ type: 'context', content: a[i - 1] });
      i--; j--;
    } else if (j > 0 && (i === 0 || dp[i][j - 1] >= dp[i - 1][j])) {
      ops.unshift({ type: 'added', content: b[j - 1] });
      j--;
    } else {
      ops.unshift({ type: 'removed', content: a[i - 1] });
      i--;
    }
  }

  return ops.map((op, idx) => ({
    type: op.type,
    content: op.content,
    lineNumber: idx + 1,
  }));
}
