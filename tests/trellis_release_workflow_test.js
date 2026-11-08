const assert = require("node:assert/strict");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const {spawnSync} = require("node:child_process");
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
  const outputs = {}, writes = [], commands = [], commandEnvs = [], secrets = [], summaries = [];
  const context = {repo: {owner: "example", repo: "repo"}, eventName: options.event || "push",
    ref: options.ref || "refs/heads/main", serverUrl: "https://github.com",
    payload: {action: "closed", pull_request: options.eventPr || pr()}};
  const env = {RELEASE_BASE: "main", RELEASE_BRANCH: "release/pending", RELEASE_MODE: options.mode || "hex",
    GLEAM_VERSION: "1.13.0", ERLANG_VERSION: "28", WORKING_DIRECTORY: ".", RELEASE_SHA: SHA,
    PREPARATION_TOKEN: "test-token", PUBLICATION_TOKEN: "publish-token",
    PRE: "", SET: "", BUMP: "", ...options.env};
  const rest = {
    git: {getRef: async () => ({data: {object: {sha: options.baseSha || SHA}}})},
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
    exec: async (command, args, options = {}) => {
      commands.push([command, ...args]);
      commandEnvs.push(options.env);
      if (args[0] === "checkout") pending = args[1] === "--detach";
    },
    getExecOutput: async (command, args, execOptions = {}) => {
      commands.push([command, ...args]);
      commandEnvs.push(execOptions);
      if (args[0] === "remote") return {stdout: options.origin || "https://github.com/example/repo"};
      if (command === "git") return {stdout: options.checkout || SHA};
      if (args[0] === "release") {
        if (options.prepareFailure) throw new Error("trellis exit 3");
        return {stdout: options.prepareOutput ?? "outcome=prepared\n"};
      }
      return {stdout: JSON.stringify({packages: [{version: pending ?
        options.pendingVersion || "1.0.0" : options.version || "1.0.0"}]})};
    },
  };
  const summary = {
    addHeading: text => {summaries.push(text); return summary;},
    addRaw: text => {summaries.push(text); return summary;},
    write: async () => {},
  };
  await new AsyncFunction("github", "context", "core", "exec", "process", source)(
    {rest, paginate}, context, {setOutput: (k,v) => outputs[k] = v, info: () => {},
      setSecret: value => secrets.push(value), summary}, exec, {env});
  return {outputs, writes, commands, commandEnvs, secrets, summaries};
}

function step(name) {
  return workflow.split(`      - name: ${name}\n`)[1].split("\n      - name:")[0];
}

function nativeShellTests() {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "trellis-workflow-"));
  try {
    fs.writeFileSync(path.join(dir, "trellis"), `#!/usr/bin/env bash
printf '%s\\n' "$@" > "$TEST_ARGS"
printf '%s\\n' "$PWD" > "$TEST_CWD"
printf '%s\\n' "\${HEXPM_API_KEY-unset}" > "$TEST_KEY"
exit "$TEST_EXIT"
`, {mode: 0o700});
    for (const [name, args] of [
      ["Publish Hex members", ["publish", "--all-untagged"]],
      ["Tag approved release", ["tag", "create", "--push", "--github-release"]],
    ]) {
      const source = step(name);
      const script = source.includes("        run: |\n")
        ? source.split("        run: |\n")[1].split("\n").map(line => line.replace(/^          /, "")).join("\n")
        : source.match(/        run: (.+)/)[1];
      assert(!script.includes("${{"), "No expression interpolation in native shell");
      for (const code of [0, 3]) {
        const summary = path.join(dir, "summary");
        fs.writeFileSync(summary, "");
        const env = {...process.env, PATH: `${dir}:${process.env.PATH}`, TEST_EXIT: String(code),
          TEST_ARGS: path.join(dir, "args"), TEST_CWD: path.join(dir, "cwd"),
          TEST_KEY: path.join(dir, "key"), GITHUB_STEP_SUMMARY: summary};
        if (name === "Publish Hex members") env.HEXPM_API_KEY = "fake-key";
        else delete env.HEXPM_API_KEY;
        const result = spawnSync("bash", ["--noprofile", "--norc", "-e", "-o", "pipefail", "-c", script], {
          cwd: dir, encoding: "utf8", env,
        });
        assert.equal(result.status, code, result.stderr);
        assert.deepEqual(fs.readFileSync(path.join(dir, "args"), "utf8").trim().split("\n"), args);
        assert.equal(fs.readFileSync(path.join(dir, "cwd"), "utf8").trim(), fs.realpathSync(dir));
        assert.equal(fs.readFileSync(path.join(dir, "key"), "utf8").trim(),
          name === "Publish Hex members" ? "fake-key" : "unset");
        assert.equal(fs.readFileSync(summary, "utf8"), "", "The outcome recorder owns summaries");
      }
    }
    const publishScript = step("Publish Hex members").split("        run: |\n")[1]
      .split("\n").map(line => line.replace(/^          /, "")).join("\n");
    fs.unlinkSync(path.join(dir, "args"));
    const missing = spawnSync("bash", ["-e", "-c", publishScript], {
      cwd: dir, encoding: "utf8", env: {...process.env, PATH: `${dir}:${process.env.PATH}`,
        HEXPM_API_KEY: "", GITHUB_STEP_SUMMARY: path.join(dir, "summary")},
    });
    assert.equal(missing.status, 1);
    assert(missing.stdout.includes("::error::hex_api_key is required"));
    assert(!fs.existsSync(path.join(dir, "args")), "Missing key must fail before CLI invocation");
  } finally {
    fs.rmSync(dir, {recursive: true, force: true});
  }
}

async function tests() {
  for (const mode of ["hex", "mixed", "git_only"]) {
    const selected = await run("select", {event: "pull_request", mode});
    assert.equal(selected.outputs.publish_sha, SHA);
    const completed = await run("publication-outcome", {mode,
      env: {TAG_OUTCOME: "success", PUBLISH_OUTCOME: mode === "git_only" ? "skipped" : "success"}});
    assert.equal(completed.writes[0].state, "success");
    assert.equal(completed.outputs.complete, "true");
    assert(completed.summaries.includes("Trellis publish"));
    assert(completed.summaries.includes("Trellis tag"));
    assert(completed.summaries.includes(`Step outcome: \`${mode === "git_only" ? "skipped" : "success"}\`.\n`));
  }
  await assert.rejects(run("select", {mode: "unknown"}), /release_mode/);
  await assert.rejects(run("select", {env: {GLEAM_VERSION: ""}}), /requires/);
  assert.equal((await run("select", {mode: "git_only", env: {GLEAM_VERSION: "", ERLANG_VERSION: ""}}))
    .outputs.prepare, "true");
  await assert.rejects(run("select", {ref: "refs/heads/other"}), /base branch/);
  await assert.rejects(run("select", {event: "pull_request_target"}), /Unsupported/);
  const earlyReservation = await run("select", {event: "workflow_dispatch"});
  assert.equal(earlyReservation.writes[0].sha, SHA);
  assert.equal(earlyReservation.writes[0].context, "trellis/release_request");
  assert.equal(earlyReservation.writes[0].state, "pending");
  await assert.rejects(run("select", {event: "workflow_dispatch", baseSha: "bad"}), /reservation base/);
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
  const reserved = await run("reserve-publication", {origin: "https://github.com/example/repo.git"});
  assert.equal(reserved.outputs.git_origin, "https://github.com/example/repo.git");
  assert.equal(reserved.outputs.git_header,
    "AUTHORIZATION: basic " + Buffer.from("x-access-token:publish-token").toString("base64"));
  assert(reserved.secrets.includes(reserved.outputs.git_header));
  for (const origin of ["https://github.com/example/repo", "https://github.com/example/repo.git"]) {
    const auth = await run("reserve-publication", {origin});
    const env = {...process.env, GIT_CONFIG_COUNT: "2",
      GIT_CONFIG_KEY_0: `http.${auth.outputs.git_origin}.extraheader`, GIT_CONFIG_VALUE_0: "",
      GIT_CONFIG_KEY_1: `http.${auth.outputs.git_origin}.extraheader`,
      GIT_CONFIG_VALUE_1: auth.outputs.git_header};
    const matched = spawnSync("git", ["config", "--get-urlmatch", "http.extraheader", origin],
      {env, encoding: "utf8"});
    assert.equal(matched.status, 0, matched.stderr);
    assert.equal(matched.stdout.trim(), auth.outputs.git_header);
    const unrelated = spawnSync("git",
      ["config", "--get-urlmatch", "http.extraheader", "https://github.com/example/other.git"],
      {env, encoding: "utf8"});
    assert(!unrelated.stdout.includes(auth.outputs.git_header), "Authorization must not reach another repo");
  }
  for (const name of ["reserve-publication", "prepare-gate"]) {
    await assert.rejects(run(name, {closed: [], origin: "https://attacker.invalid/example/repo"}), /origin/);
  }
  await assert.rejects(run("reserve-publication", {env: {PUBLICATION_TOKEN: "bad token"}}), /token/);
  for (const mode of ["hex", "git_only", "mixed"]) {
    const failed = await run("publication-outcome", {mode, env: {TAG_OUTCOME: "failure", PUBLISH_OUTCOME: "success"}});
    assert.equal(failed.writes[0].state, "failure");
    assert.deepEqual(failed.outputs, {});
    assert(failed.summaries.includes("Step outcome: `failure`.\n"));
  }
  const skipped = await run("publication-outcome", {env: {TAG_OUTCOME: "skipped", PUBLISH_OUTCOME: "failure"}});
  assert.equal(skipped.writes[0].state, "failure");
  assert(skipped.summaries.includes("Step outcome: `skipped`.\n"));
  const notRun = await run("publication-outcome");
  assert.equal(notRun.writes[0].state, "failure");
  assert(notRun.summaries.includes("Step outcome: `not run`.\n"));
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
  assert.deepEqual((await run("prepare-gate", {closed: [], statuses: {
    [SHA]: [{context: "trellis/release_request", state: "pending"}]},
  })).outputs, {}); // App-token, checkout, or install failure cannot hand ownership to a push.
  assert.deepEqual((await run("prepare-gate", {statuses: reservation, commits: [OLD, SHA]})).outputs, {});
  assert.deepEqual((await run("prepare-gate", {statuses: reservation, commits: [OLD], closed: []})).outputs, {});
  assert.deepEqual((await run("prepare-gate", {statuses: success, version: "1.1.0-rc.0"})).outputs, {});
  const candidate = await run("prepare-gate", {statuses: success, open: [pr()], pendingVersion: "1.1.0-rc.0"});
  assert.deepEqual(candidate.outputs, {});
  assert(candidate.commands.some(c => c.join(" ") === "git checkout main"));
  const authenticatedFetch = candidate.commandEnvs.find(env => env?.GIT_CONFIG_COUNT);
  assert.equal(authenticatedFetch.GIT_CONFIG_COUNT, "2");
  assert.equal(authenticatedFetch.GIT_CONFIG_KEY_1, "http.https://github.com/example/repo.extraheader");
  assert.equal(authenticatedFetch.GIT_CONFIG_VALUE_0, "");
  assert.equal(authenticatedFetch.GIT_CONFIG_VALUE_1,
    "AUTHORIZATION: basic " + Buffer.from("x-access-token:test-token").toString("base64"));
  await assert.rejects(run("prepare-gate", {statuses: success, open: [pr()],
    env: {PREPARATION_TOKEN: ""}}), /preparation token/);
  const retry = await run("prepare-gate", {event: "workflow_dispatch", statuses: reservation, commits: [OLD, SHA]});
  assert.deepEqual(JSON.parse(retry.outputs.reservation_shas), [OLD, SHA]);
  const noop = await run("clear-noop", {env: {RESERVATION_SHAS: JSON.stringify([OLD, SHA])}, open: []});
  assert.equal(noop.writes[0].sha, OLD);
  assert.equal(noop.writes[0].state, "success");
  assert.equal(noop.writes[1].sha, SHA);
  assert.deepEqual((await run("clear-noop", {open: [pr()]})).writes, []);

  for (const outcome of ["prepared", "unchanged", "no_changes"]) {
    const prepared = await run("prepare", {prepareOutput: `outcome=${outcome}\npr_url=https://example.invalid/pr\n`,
      env: {PRE: " none ", SET: " a=1.3.0 \r\n\nb=$(touch bad)\n c=has spaces ",
        BUMP: "a=minor\r\nb=patch", WORKING_DIRECTORY: "packages/with spaces"}});
    assert.deepEqual(prepared.commands, [["trellis", "release", "pr", "--base", "main",
      "--branch", "release/pending", "--github-output", "--pre", "none",
      "--set", "a=1.3.0", "--set", "b=$(touch bad)", "--set", "c=has spaces",
      "--bump", "a=minor", "--bump", "b=patch"]]);
    assert.equal(prepared.commandEnvs[0].cwd, "packages/with spaces");
    assert(prepared.summaries.some(text => text.includes(`\`${outcome}\``)));
  }
  assert.deepEqual((await run("prepare")).commands[0].slice(1),
    ["release", "pr", "--base", "main", "--branch", "release/pending", "--github-output"]);
  await assert.rejects(run("prepare", {prepareFailure: true}), /exit 3/);
  for (const output of ["", "outcome=bad\n"]) {
    await assert.rejects(run("prepare", {prepareOutput: output}), /preparation outcome/);
  }
  nativeShellTests();
  for (const [name, authStep, token] of [
    ["Tag approved release", "reserve", "secrets.publication_token || github.token"],
    ["Prepare release PR", "gate", "steps.app.outputs.token"],
  ]) {
    const source = step(name);
    assert(source.includes(`GH_TOKEN: \${{ ${token} }}`));
    assert(source.includes(`GITHUB_TOKEN: \${{ ${token} }}`));
    assert(source.includes("GIT_CONFIG_COUNT: '2'"));
    assert(source.includes(`GIT_CONFIG_KEY_0: http.\${{ steps.${authStep}.outputs.git_origin }}.extraheader`));
    assert(source.includes("GIT_CONFIG_VALUE_0: ''"));
    assert(source.includes(`GIT_CONFIG_KEY_1: http.\${{ steps.${authStep}.outputs.git_origin }}.extraheader`));
    assert(source.includes(`GIT_CONFIG_VALUE_1: \${{ steps.${authStep}.outputs.git_header }}`));
    assert(!source.includes("GITHUB_ENV") && !source.includes("git config"));
  }
  assert.equal((workflow.match(/persist-credentials: false/g) || []).length, 2);
  assert(!/uses: .*\/trellis-(release-pr|publish|tag)@/.test(workflow));
  assert(step("Tag approved release").includes("if: steps.select.outputs.publish_sha != ''"));
  assert(!step("Tag approved release").includes("always()"), "Failed publication must skip tags");
  assert(step("Publish Hex members").includes("inputs.release_mode != 'git_only'"));
  assert(step("Prepare release PR").includes("if: steps.gate.outputs.prepare == 'true'"));
  assert.equal((step("Prepare release PR").match(/github.event_name == 'workflow_dispatch'/g) || []).length, 3);
  assert(workflow.indexOf("- name: Publish Hex members") < workflow.indexOf("- name: Tag approved release"));
  assert(workflow.indexOf("- name: Tag approved release") < workflow.indexOf("- name: Record publication outcome"));
  assert(workflow.includes("queue: max") && workflow.includes("cancel-in-progress: false"));
  assert(workflow.includes("trellis-release-${{ github.repository }}"));
  assert(workflow.includes("ref: ${{ steps.select.outputs.publish_sha }}"));
  assert(workflow.includes("ref: ${{ inputs.base }}"));
  assert(workflow.includes("steps.prepare.outcome == 'success' && steps.gate.outputs.reservation_sha != ''"));
  assert.equal((workflow.match(/HEXPM_API_KEY: \$\{\{ secrets.hex_api_key \}\}/g) || []).length, 1);
  for (const line of workflow.split("\n").filter(l => /^\s*(?:-\s*)?uses:/.test(l))) {
    assert.match(line, /@[0-9a-f]{40} # ratchet:/);
  }
  console.log("trellis release workflow: direct CLI, scoped auth, trust, ownership, recovery, and modes passed");
}
tests().catch(error => {console.error(error); process.exitCode = 1;});
