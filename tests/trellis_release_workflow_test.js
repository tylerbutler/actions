const assert = require("node:assert/strict");
const fs = require("node:fs");
const workflow = fs.readFileSync(".github/workflows/trellis-release.yml", "utf8");
const AsyncFunction = Object.getPrototypeOf(async function () {}).constructor;
const SHA = "a".repeat(40);
const OLD = "b".repeat(40);
const pr = (extra = {}) => ({
  number: 1, merged: true, merged_at: "2026-11-01T00:00:00Z", merge_commit_sha: SHA,
  head: {ref: "release/pending", sha: SHA, repo: {full_name: "example/repo"}},
  base: {ref: "main", repo: {full_name: "example/repo"}}, ...extra,
});

async function run(name, options = {}) {
  const source = workflow.match(new RegExp(`// script: ${name}\\n([\\s\\S]*?)// end-script`))[1];
  const outputs = {}, writes = [], commands = [];
  const context = {repo: {owner: "example", repo: "repo"}, eventName: options.event || "push",
    ref: options.ref || "refs/heads/main", payload: {action: "closed", pull_request: options.eventPr || pr()}};
  const env = {RELEASE_BASE: "main", RELEASE_BRANCH: "release/pending", RELEASE_MODE: options.mode || "hex",
    GLEAM_VERSION: "1.13.0", ERLANG_VERSION: "28", WORKING_DIRECTORY: ".", RELEASE_SHA: SHA,
    ...options.env};
  const rest = {
    pulls: {get: async () => ({data: options.pr || pr()}), list: "pulls"},
    repos: {
      listCommitStatusesForRef: "statuses", listCommits: "commits",
      compareCommitsWithBasehead: async () => ({data: {status: options.comparison || "ahead"}}),
      createCommitStatus: async value => {writes.push(value);},
    },
  };
  const paginate = async (method, args) => {
    if (method === "statuses") return options.statuses?.[args.ref] || [];
    if (method === "pulls") return args.state === "open" ? options.open || [] : options.closed || [pr()];
    throw new Error("Unexpected endpoint");
  };
  paginate.iterator = async function* () { yield {data: (options.commits || [SHA]).map(sha => ({sha}))}; };
  let pending = false;
  const exec = {
    exec: async (command, args) => {
      commands.push([command, ...args]);
      if (args[0] === "checkout") pending = args[1] === "--detach";
    },
    getExecOutput: async (command, args) => {
      commands.push([command, ...args]);
      if (command === "git") return {stdout: options.checkout || SHA};
      return {stdout: JSON.stringify({packages: [{version: pending ?
        options.pendingVersion || "1.0.0" : options.version || "1.0.0"}]})};
    },
  };
  await new AsyncFunction("github", "context", "core", "exec", "process", source)(
    {rest, paginate}, context, {setOutput: (k,v) => outputs[k] = v, info: () => {}}, exec, {env});
  return {outputs, writes, commands};
}

async function tests() {
  for (const mode of ["hex", "mixed", "git_only"]) {
    const selected = await run("select", {event: "pull_request", mode});
    assert.equal(selected.outputs.publish_sha, SHA);
    const completed = await run("publication-outcome", {mode,
      env: {TAG_OUTCOME: "success", PUBLISH_OUTCOME: mode === "git_only" ? "skipped" : "success"}});
    assert.equal(completed.writes[0].state, "success");
    assert.equal(completed.outputs.complete, "true");
  }
  await assert.rejects(run("select", {mode: "unknown"}), /release_mode/);
  await assert.rejects(run("select", {env: {GLEAM_VERSION: ""}}), /requires/);
  assert.equal((await run("select", {mode: "git_only", env: {GLEAM_VERSION: "", ERLANG_VERSION: ""}}))
    .outputs.prepare, "true");
  await assert.rejects(run("select", {ref: "refs/heads/other"}), /base branch/);
  await assert.rejects(run("select", {event: "pull_request_target"}), /Unsupported/);
  const fork = pr({head: {ref: "release/pending", repo: {full_name: "attacker/repo"}}});
  assert.deepEqual((await run("select", {event: "pull_request", pr: fork})).outputs, {});
  assert.deepEqual((await run("select", {event: "pull_request", pr: pr({merged: false})})).outputs, {});
  assert.deepEqual((await run("select", {event: "pull_request",
    pr: pr({base: {ref: "other", repo: {full_name: "example/repo"}}})})).outputs, {});
  await assert.rejects(run("select", {event: "pull_request", eventPr: pr({merge_commit_sha: OLD})}), /merge state/);
  await assert.rejects(run("select", {event: "pull_request", comparison: "diverged"}), /not on/);
  await assert.rejects(run("select", {event: "pull_request",
    closed: [pr({merge_commit_sha: OLD, merged_at: "2026-11-02"})]}), /newer release/);
  const completedOld = await run("select", {event: "pull_request",
    statuses: {[SHA]: [{context: "trellis/release", state: "success"}]},
    closed: [pr({merge_commit_sha: OLD, merged_at: "2026-11-02"})]});
  assert.deepEqual(completedOld.outputs, {prepare: "true"});
  await assert.rejects(run("reserve-publication", {checkout: OLD}), /checkout changed/);
  assert.equal((await run("reserve-publication")).writes[0].state, "pending");
  for (const mode of ["hex", "git_only", "mixed"]) {
    const failed = await run("publication-outcome", {mode, env: {TAG_OUTCOME: "failure", PUBLISH_OUTCOME: "success"}});
    assert.equal(failed.writes[0].state, "failure");
    assert.deepEqual(failed.outputs, {});
  }
  assert.equal((await run("publication-outcome", {env: {TAG_OUTCOME: "success", PUBLISH_OUTCOME: "failure"}}))
    .writes[0].state, "failure");
  for (const state of [null, "pending", "failure"]) {
    const statuses = state ? {[SHA]: [{context: "trellis/release", state}]} : {};
    assert.deepEqual((await run("prepare-gate", {event: "workflow_dispatch", statuses})).outputs, {});
  }
  const success = {[SHA]: [{context: "trellis/release", state: "success"}]};
  assert.equal((await run("prepare-gate", {statuses: success})).outputs.prepare, "true");
  const manual = await run("prepare-gate", {event: "workflow_dispatch", statuses: success});
  assert.equal(manual.outputs.reservation_sha, SHA);
  assert.equal(manual.writes[0].context, "trellis/release_request");
  assert.equal(manual.writes[0].state, "pending");
  const reservation = {...success, [OLD]: [{context: "trellis/release_request", state: "pending"}]};
  assert.deepEqual((await run("prepare-gate", {statuses: reservation, commits: [OLD, SHA]})).outputs, {});
  assert.deepEqual((await run("prepare-gate", {statuses: reservation, commits: [OLD], closed: []})).outputs, {});
  assert.deepEqual((await run("prepare-gate", {statuses: success, version: "1.1.0-rc.0"})).outputs, {});
  const candidate = await run("prepare-gate", {statuses: success, open: [pr()], pendingVersion: "1.1.0-rc.0"});
  assert.deepEqual(candidate.outputs, {});
  assert(candidate.commands.some(c => c.join(" ") === "git checkout main"));
  const retry = await run("prepare-gate", {event: "workflow_dispatch", statuses: reservation, commits: [OLD, SHA]});
  assert.deepEqual(JSON.parse(retry.outputs.reservation_shas), [OLD, SHA]);
  const noop = await run("clear-noop", {env: {RESERVATION_SHAS: JSON.stringify([OLD, SHA])}, open: []});
  assert.equal(noop.writes[0].sha, OLD);
  assert.equal(noop.writes[0].state, "success");
  assert.equal(noop.writes[1].sha, SHA);
  assert.deepEqual((await run("clear-noop", {open: [pr()]})).writes, []);

  assert(workflow.includes("queue: max") && workflow.includes("cancel-in-progress: false"));
  assert(workflow.includes("trellis-release-${{ github.repository }}"));
  assert(workflow.includes("ref: ${{ steps.select.outputs.publish_sha }}"));
  assert(workflow.includes("ref: ${{ inputs.base }}"));
  assert(workflow.includes("steps.prepare.outcome == 'success' && steps.gate.outputs.reservation_sha != ''"));
  assert.equal((workflow.match(/hex_api_key: \$\{\{ secrets.hex_api_key \}\}/g) || []).length, 1);
  for (const line of workflow.split("\n").filter(l => /^\s*(?:-\s*)?uses:/.test(l))) {
    assert.match(line, /@[0-9a-f]{40} # ratchet:/);
  }
  console.log("trellis release workflow: trust, ownership, recovery, and modes passed");
}
tests().catch(error => {console.error(error); process.exitCode = 1;});
