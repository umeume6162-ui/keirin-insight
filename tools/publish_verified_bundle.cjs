#!/usr/bin/env node
'use strict';

// Publish all four VERIFIED feeds through one GitHub Git Data API commit.
// No separate per-file commits; GitHub's existing CI checks the final snapshot.
const fs = require('node:fs');
const path = require('node:path');
const names = [
  'verified-rider-ids-feed-v1.json',
  'verified-results-feed-v1.json',
  'verified-rider-results-feed-v1.json',
  'verified-line-snapshots-feed-v1.json'
];

const args = process.argv.slice(2);
function option(flag) {
  const i = args.indexOf(flag);
  return i < 0 ? null : args[i + 1];
}
function fail(message) { throw new Error(message); }

async function main() {
  const stage = option('--staged-dir');
  const expected = option('--expected-head');
  const branch = option('--branch') || 'main';
  const apply = args.includes('--apply');
  const repo = process.env.GITHUB_REPOSITORY || option('--repo');
  if (!stage || !repo || !/^[^/\s]+\/[^/\s]+$/.test(repo)) {
    fail('Specify --staged-dir and GITHUB_REPOSITORY=owner/repo (or --repo).');
  }
  if (apply && (!expected || !/^[0-9a-f]{40}$/i.test(expected))) {
    fail('--apply requires an exact --expected-head commit SHA to prevent stale writes.');
  }
  if (!/^[a-zA-Z0-9._/-]+$/.test(branch) || branch.includes('..')) {
    fail('Invalid branch name.');
  }
  const files = names.map(name => {
    const text = fs.readFileSync(path.join(stage, name), 'utf8');
    JSON.parse(text); // Input structure is validated once by the existing publication CI.
    return {path: name, mode: '100644', type: 'blob', content: text};
  });
  if (!apply) {
    process.stdout.write('DRY RUN: parsed four staged JSON feeds; no remote write performed.\n');
    return;
  }
  const token = process.env.GITHUB_TOKEN;
  if (!token) fail('GITHUB_TOKEN is required for --apply.');
  const prefix = '/repos/' + repo;
  async function request(method, route, payload) {
    const response = await fetch('https://api.github.com' + prefix + route, {
      method,
      headers: {
        Accept: 'application/vnd.github+json',
        Authorization: 'Bearer ' + token,
        'X-GitHub-Api-Version': '2022-11-28',
        'User-Agent': 'keirin-insight-atomic-publisher',
        'Content-Type': 'application/json'
      },
      body: payload === undefined ? undefined : JSON.stringify(payload)
    });
    if (!response.ok) {
      // Never print response bodies: API errors can contain sensitive context.
      fail('GitHub API ' + method + ' ' + route + ' failed (HTTP ' + response.status + ').');
    }
    return response.json();
  }
  const refPath = '/git/ref/heads/' + branch.split('/').map(encodeURIComponent).join('/');
  const head = (await request('GET', refPath)).object.sha;
  if (head !== expected) fail('Branch moved since source snapshot; rebuild bundle from current main.');
  const base = await request('GET', '/git/commits/' + head);
  const tree = await request('POST', '/git/trees', {base_tree: base.tree.sha, tree: files});
  const commit = await request('POST', '/git/commits', {
    message: 'Publish four verified feeds atomically',
    tree: tree.sha,
    parents: [head]
  });
  const recheckedHead = (await request('GET', refPath)).object.sha;
  if (recheckedHead !== head) fail('Concurrent update detected; no ref was changed.');
  // Non-forced fast-forward rejects concurrent updates even after the final check.
  await request('PATCH', '/git/refs/heads/' + branch.split('/').map(encodeURIComponent).join('/'), {
    sha: commit.sha, force: false
  });
  process.stdout.write('Published four verified feeds in one commit: ' + commit.sha + '\n');
}
main().catch(e => { process.stderr.write('ABORT: ' + e.message + '\n'); process.exitCode = 1; });
