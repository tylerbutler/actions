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
      if (options.nativeExec) return options.nativeExec(command, args);
      if (args[0] === "remote") return {stdout: options.origin || "https://github.com/example/repo"};
      if (command === "git") return {stdout: options.checkout || SHA};
      if (args[0] === "list" && options.packageList) return {stdout: JSON.stringify(options.packageList)};
      if (args[0] === "ci" && args[1] === "outputs") return {stdout: options.ciOutputs ?? ""};
      if (args[0] === "ci" && args[1] === "tag-package") {
        if (!options.tagPackages?.[args[2]]) throw new Error("Tag resolver failed");
        return {stdout: JSON.stringify(options.tagPackages[args[2]])};
      }
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

function shell(name) {
  return step(name).split("        run: |\n")[1].split("\n")
    .map(line => line.replace(/^          /, "")).join("\n");
}

function sbomShellTests() {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "trellis-sbom-test-"));
  const git = spawnSync("which", ["git"], {encoding: "utf8"}).stdout.trim();
  const command = (name, args) => {
    const result = spawnSync(name, args, {cwd: dir, encoding: "utf8"});
    assert.equal(result.status, 0, result.stderr);
    return result.stdout.trim();
  };
  try {
    const bin = path.join(dir, "bin"), assets = path.join(dir, "assets");
    fs.mkdirSync(bin); fs.mkdirSync(assets);
    fs.writeFileSync(path.join(dir, "gleam.toml"),
      'name="shelf"\nversion="1.0.0"\n[dependencies]\nruntime="1"\n[dev-dependencies]\ntests="1"\n');
    const manifest = '[[packages]]\nname="runtime"\nversion="1.0.0"\nrequirements=["shared"]\n'
      + '[[packages]]\nname="shared"\nversion="1.0.0"\nrequirements=[]\n'
      + '[[packages]]\nname="tests"\nversion="1.0.0"\nrequirements=["shared","dev"]\n'
      + '[[packages]]\nname="dev"\nversion="1.0.0"\nrequirements=[]\n';
    fs.writeFileSync(path.join(dir, "manifest.toml"), manifest);
    command(git, ["init", "-q"]);
    command(git, ["config", "user.name", "Test"]);
    command(git, ["config", "user.email", "test@example.invalid"]);
    command(git, ["add", "gleam.toml", "manifest.toml"]);
    command(git, ["commit", "-qm", "approved"]);
    const sha = command(git, ["rev-parse", "HEAD"]);
    command(git, ["remote", "add", "origin", dir]);
    const document = {bomFormat: "CycloneDX", specVersion: "1.6",
      metadata: {component: {name: "shelf", version: "1.0.0"}},
      components: ["runtime", "shared", "tests", "dev"].map(name => ({
        name, version: "1.0.0", scope: ["runtime", "shared"].includes(name) ? "required" : "optional",
      }))};
    fs.writeFileSync(path.join(dir, "document.json"), JSON.stringify(document));
    // Real nested Hex archives exercise byte comparison rather than mocking tar/cmp.
    command("python3", ["-c", `
import io, pathlib, tarfile
root = pathlib.Path(".")
data = (root / "document.json").read_bytes()
def archive(data, output):
    inner = io.BytesIO()
    with tarfile.open(fileobj=inner, mode="w:gz") as contents:
        entry = tarfile.TarInfo("priv/shelf.cdx.json")
        entry.size = len(data)
        contents.addfile(entry, io.BytesIO(data))
    payload = inner.getvalue()
    with tarfile.open(output, mode="w") as package:
        entry = tarfile.TarInfo("contents.tar.gz")
        entry.size = len(payload)
        package.addfile(entry, io.BytesIO(payload))
archive(data, "package.tar")
archive(b"mismatched", "wrong.tar")
`]);
    const nativeDir = path.join(dir, "licence_audit-v0.15.0-x86_64-linux-glibc");
    fs.mkdirSync(nativeDir);
    fs.writeFileSync(path.join(nativeDir, "licence_audit"),
      '#!/usr/bin/env bash\nprintf "0.15.0\\n"\n', {mode: 0o700});
    const archive = "licence_audit-v0.15.0-x86_64-linux-glibc.tar.gz";
    command("tar", ["-czf", archive, path.basename(nativeDir)]);
    const hash = require("node:crypto").createHash("sha256").update(fs.readFileSync(path.join(dir, archive))).digest("hex");
    fs.writeFileSync(path.join(dir, "checksums.txt"), `${hash}  ${archive}\n`);
    const fake = `#!/usr/bin/env node
const fs = require("node:fs"), path = require("node:path"), cp = require("node:child_process");
const name = path.basename(process.argv[1]), args = process.argv.slice(2), env = process.env;
const root = env.TEST_ROOT;
fs.appendFileSync(path.join(root, "commands"), JSON.stringify({name, args,
  secrets: ["GH_TOKEN","GITHUB_TOKEN","HEXPM_API_KEY","GIT_CONFIG_VALUE_1"]
    .filter(key => env[key]).map(key => [key, env[key]])}) + "\\n");
if (env.TEST_FAIL === name) process.exit(3);
const copy = (source, target) => fs.copyFileSync(path.join(root, source), target);
if (name === "git") {
  const result = cp.spawnSync(env.TEST_GIT, args, {stdio: "inherit"});
  process.exit(result.status);
} else if (name === "gleam") {
  if (args[0] === "deps" && env.TEST_MUTATE_LOCK) fs.appendFileSync("manifest.toml", "\\n# changed\\n");
  if (args[0] === "export") {
    fs.mkdirSync("build", {recursive:true});
    copy(env.TEST_EXPORT || "package.tar", "build/shelf-1.0.0.tar");
  }
} else if (name === "licence_audit") {
  if (env.SOURCE_DATE_EPOCH !== "0") throw new Error("Unfixed generation epoch");
  copy("document.json", args.find(arg => arg.startsWith("--output=")).slice(9));
  if (env.TEST_CHANGE_HEAD) cp.execFileSync(env.TEST_GIT, ["checkout", "--detach", env.TEST_CHANGE_HEAD]);
} else if (name === "curl") {
  const url = args.find(arg => arg.startsWith("https://")), target = args[args.indexOf("-o")+1];
  if (url.startsWith("https://repo.hex.pm/")) copy(env.TEST_HEX || "package.tar", target);
  else copy(url.endsWith("checksums.txt") ? "checksums.txt" : "${archive}", target);
} else if (name === "trellis") {
  if (args[0] === "publish") {
    if (!fs.existsSync(path.join(root, "published"))) fs.writeFileSync(path.join(root, "published"), "1");
  } else if (args[0] === "tag") {
    const found = cp.spawnSync(env.TEST_GIT, ["rev-parse","--verify","refs/tags/shelf-v1.0.0"], {stdio:"ignore"});
    if (found.status !== 0) cp.execFileSync(env.TEST_GIT, ["tag","shelf-v1.0.0"]);
  } else throw new Error("Unexpected Trellis command");
} else if (name === "gh") {
  const target = path.join(root, "assets", "shelf-v1.0.0.cdx.json");
  if (args[1] === "view") console.log(JSON.stringify({assets: fs.existsSync(target) ? [{name:path.basename(target)}] : []}));
  else if (args[1] === "upload") {
    if (env.TEST_UPLOAD_FAIL) process.exit(3);
    if (fs.existsSync(target)) throw new Error("No clobber");
    fs.copyFileSync(args[3], target);
  } else if (args[1] === "download") {
    fs.copyFileSync(target, path.join(args[args.indexOf("--dir")+1], path.basename(target)));
  } else throw new Error("Unexpected gh command");
} else throw new Error("Unexpected tool");
`;
    for (const name of ["git", "gleam", "licence_audit", "curl", "trellis", "gh"]) {
      fs.writeFileSync(path.join(bin, name), fake, {mode: 0o700});
    }
    const output = path.join(dir, "output"), commands = path.join(dir, "commands");
    const env = {...process.env, PATH: `${bin}:${process.env.PATH}`, TEST_ROOT: dir, TEST_GIT: git,
      RUNNER_TEMP: dir, GITHUB_OUTPUT: output, GITHUB_PATH: path.join(dir, "tool-path"),
      RELEASE_SHA: sha, SBOM_PACKAGE: "shelf", SBOM_VERSION: "1.0.0", SBOM_PATH: "priv/shelf.cdx.json",
      SBOM_ASSET: "shelf-v1.0.0.cdx.json", SBOM_TAG: "shelf-v1.0.0", LICENCE_AUDIT_VERSION: "0.15.0",
      SOURCE_DATE_EPOCH: "0"};
    for (const key of Object.keys(env)) {
      if (["GH_TOKEN","GITHUB_TOKEN","HEXPM_API_KEY","GIT_CONFIG_COUNT"].includes(key)
          || key.startsWith("GIT_CONFIG_KEY_") || key.startsWith("GIT_CONFIG_VALUE_")) delete env[key];
    }
    const execute = (name, extra = {}, expected = 0) => {
      const result = spawnSync("bash", ["--noprofile", "--norc", "-e", "-o", "pipefail", "-c", shell(name)], {
        cwd: dir, env: {...env, ...extra}, encoding: "utf8",
      });
      if (expected === 0) assert.equal(result.status, 0, `${name}: ${result.stderr}\n${result.stdout}`);
      else assert.notEqual(result.status, 0, `${name} must fail`);
      return result;
    };
    const calls = () => fs.readFileSync(commands, "utf8").trim().split("\n").map(JSON.parse);
    execute("Install native licence_audit");
    assert(fs.readFileSync(env.GITHUB_PATH, "utf8").includes("licence-audit."));
    fs.writeFileSync(path.join(dir, "checksums.txt"), `${"0".repeat(64)}  ${archive}\n`);
    execute("Install native licence_audit", {}, 1);
    fs.writeFileSync(path.join(dir, "checksums.txt"), "");
    execute("Install native licence_audit", {}, 1);
    fs.writeFileSync(path.join(dir, "checksums.txt"), `${hash}  ${archive}\n`);
    execute("Install native licence_audit", {TEST_FAIL: "curl"}, 1);
    execute("Generate and verify package SBOM", {RELEASE_SHA: OLD}, 1);
    execute("Generate and verify package SBOM", {TEST_FAIL: "licence_audit"}, 1);
    execute("Generate and verify package SBOM", {TEST_MUTATE_LOCK: "true"}, 1);
    fs.writeFileSync(path.join(dir, "manifest.toml"), manifest);
    execute("Generate and verify package SBOM", {TEST_EXPORT: "wrong.tar"}, 1);
    for (const bad of [
      {...document, specVersion: "1.5"},
      {...document, metadata: {component: {name: "other", version: "1.0.0"}}},
      {...document, components: document.components.slice(1)},
      {...document, components: document.components.map(c => ({...c, scope: "required"}))},
    ]) {
      fs.writeFileSync(path.join(dir, "document.json"), JSON.stringify(bad));
      execute("Generate and verify package SBOM", {}, 1);
    }
    fs.writeFileSync(path.join(dir, "document.json"), JSON.stringify(document));
    execute("Generate and verify package SBOM");
    env.SBOM_SNAPSHOT = fs.readFileSync(output, "utf8").trim().split("\n").at(-1).slice("snapshot=".length);
    assert.equal(fs.readFileSync(env.SBOM_SNAPSHOT, "utf8"), JSON.stringify(document));
    const generation = calls().filter(c => ["gleam", "licence_audit"].includes(c.name));
    assert(generation.every(c => c.secrets.length === 0), "Generation must not receive release secrets");
    assert(generation.some(c => c.name === "licence_audit" &&
      c.args.join(" ") === "sbom --reproducible --output=priv/shelf.cdx.json"));
    const publish = shell("Publish Hex members");
    const publishRun = () => {
      const result = spawnSync("bash", ["-e", "-c", publish], {
        cwd: dir, env: {...env, HEXPM_API_KEY: "fake-hex"}, encoding: "utf8",
      });
      assert.equal(result.status, 0, result.stderr);
    };
    publishRun();
    execute("Verify published Hex SBOM", {TEST_HEX: "wrong.tar"}, 1);
    execute("Verify published Hex SBOM", {TEST_FAIL: "curl"}, 1);
    execute("Verify published Hex SBOM");
    command(git, ["tag", "shelf-v1.0.0"]);
    const asset = path.join(assets, env.SBOM_ASSET);
    execute("Reconcile GitHub Release SBOM", {GH_TOKEN: "fake-publish", TEST_UPLOAD_FAIL: "true"}, 1);
    assert(!fs.existsSync(asset));
    // Recovery invokes the CLI again, but its published-version check skips republishing.
    publishRun();
    assert.equal(fs.readFileSync(path.join(dir, "published"), "utf8"), "1");
    execute("Generate and verify package SBOM");
    execute("Verify published Hex SBOM");
    execute("Reconcile GitHub Release SBOM", {GH_TOKEN: "fake-publish"});
    assert.deepEqual(fs.readFileSync(asset), fs.readFileSync(env.SBOM_SNAPSHOT));
    const uploads = calls().filter(c => c.name === "gh" && c.args[1] === "upload").length;
    execute("Reconcile GitHub Release SBOM", {GH_TOKEN: "fake-publish"});
    assert.equal(calls().filter(c => c.name === "gh" && c.args[1] === "upload").length, uploads);
    fs.writeFileSync(asset, "different");
    execute("Reconcile GitHub Release SBOM", {GH_TOKEN: "fake-publish"}, 1);
    assert.equal(fs.readFileSync(asset, "utf8"), "different");
    command(git, ["commit", "--allow-empty", "-qm", "other"]);
    const other = command(git, ["rev-parse", "HEAD"]);
    command(git, ["checkout", "--detach", sha]);
    command(git, ["tag", "-f", "shelf-v1.0.0", other]);
    execute("Reconcile GitHub Release SBOM", {GH_TOKEN: "fake-publish"}, 1);
    execute("Generate and verify package SBOM", {TEST_CHANGE_HEAD: other}, 1);
    assert(calls().filter(c => c.name === "gh").every(c => !c.args.includes("--clobber")));
  } finally {
    fs.rmSync(dir, {recursive: true, force: true});
  }
}

async function nativeTaggedRetryTests() {
  if (!process.env.SBOM_TEST_TRELLIS_BIN) return;
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "trellis-native-tagged-"));
  const command = (name, args) => {
    const result = spawnSync(name, args, {cwd: dir, encoding: "utf8"});
    assert.equal(result.status, 0, `${name}: ${result.stderr}\n${result.stdout}`);
    return result.stdout;
  };
  try {
    command("git", ["init", "-q"]);
    command("git", ["config", "user.name", "Test"]);
    command("git", ["config", "user.email", "test@example.invalid"]);
    const select = () => run("sbom-select", {env: {SBOM_PACKAGE: "fixture"},
      nativeExec: (name, args) => {
        assert.equal(name, "trellis");
        return {stdout: command(process.env.SBOM_TEST_TRELLIS_BIN, args)};
      }});
    for (const [format, expected] of [["v{version}", "v1.0.0"],
      ["release-{name}-v{version}", "release-fixture-v1.0.0"]]) {
      fs.writeFileSync(path.join(dir, "gleam.toml"),
        'name="fixture"\nversion="1.0.0"\n[tools.trellis.publish]\n'
        + `exact_tag_format="${format}"\n`);
      command("git", ["add", "gleam.toml"]);
      command("git", ["commit", "-qm", "approved"]);
      const initial = await select();
      assert.equal(initial.outputs.tag, expected);
      const pending = JSON.parse(command(process.env.SBOM_TEST_TRELLIS_BIN, ["tag", "plan", "--json"]));
      assert(pending.tags.some(t => t.kind === "exact" && t.tag === expected),
        "Configured tag must agree with the native untagged plan");
      command("git", ["tag", "-a", initial.outputs.tag, "-m", "already tagged"]);
      const plan = JSON.parse(command(process.env.SBOM_TEST_TRELLIS_BIN, ["tag", "plan", "--json"]));
      assert.deepEqual(plan.tags, [], "Native tag plan omits an already tagged current version");
      const retry = await select();
      assert.deepEqual(retry.outputs, initial.outputs, "Tagged retry must retain the same SBOM asset identity");
      assert(!retry.commands.some(c => c[1] === "tag"), "Selection must not mutate/reconcile tags");
    }
    console.log("native Trellis 1.3.0: custom-format annotated existing-tag retry passed");
  } finally {
    fs.rmSync(dir, {recursive: true, force: true});
  }
}

async function nativeSbomContractTests() {
  if (!process.env.SBOM_TEST_TRELLIS_BIN || !process.env.SBOM_TEST_LICENCE_AUDIT_BIN) return;
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "trellis-native-sbom-"));
  const env = {...process.env};
  for (const key of ["GH_TOKEN", "GITHUB_TOKEN", "HEXPM_API_KEY"]) delete env[key];
  const command = (name, args) => {
    const result = spawnSync(name, args, {cwd: dir, env, encoding: "utf8"});
    assert.equal(result.status, 0, `${name}: ${result.stderr}\n${result.stdout}`);
    return result.stdout.trim();
  };
  try {
    fs.mkdirSync(path.join(dir, "src"));
    fs.mkdirSync(path.join(dir, "bin"));
    fs.writeFileSync(path.join(dir, "src", "fixture.gleam"), "pub fn main() { Nil }\n");
    fs.writeFileSync(path.join(dir, "gleam.toml"),
      'name="fixture"\nversion="1.0.0"\ndescription="SBOM fixture"\nlicences=["MIT"]\n'
      + '[dependencies]\ngleam_stdlib=">= 0.44.0 and < 1.0.0"\n'
      + '[dev-dependencies]\ngleeunit=">= 1.0.0 and < 2.0.0"\n');
    fs.writeFileSync(path.join(dir, ".gitignore"), "/build/\n/priv/*.cdx.json\n");
    command("git", ["init", "-q"]);
    command("git", ["config", "user.name", "Test"]);
    command("git", ["config", "user.email", "test@example.invalid"]);
    command("gleam", ["deps", "download"]);
    command("git", ["add", "gleam.toml", "manifest.toml", "src", ".gitignore"]);
    command("git", ["commit", "-qm", "approved"]);
    const sha = command("git", ["rev-parse", "HEAD"]);
    const metadata = await run("sbom-select", {env: {SBOM_PACKAGE: "fixture"},
      nativeExec: (name, args) => {
        assert.equal(name, "trellis");
        return {stdout: command(process.env.SBOM_TEST_TRELLIS_BIN, args)};
      }});
    assert.equal(metadata.outputs.version, "1.0.0");
    const version = command(process.env.SBOM_TEST_LICENCE_AUDIT_BIN, ["--version"]);
    assert.equal(version, "0.15.0");
    fs.symlinkSync(process.env.SBOM_TEST_LICENCE_AUDIT_BIN, path.join(dir, "bin", "licence_audit"));
    const output = path.join(dir, "output");
    Object.assign(env, {PATH: `${path.join(dir, "bin")}:${env.PATH}`, RELEASE_SHA: sha,
      SBOM_PACKAGE: "fixture", SBOM_VERSION: metadata.outputs.version, SBOM_PATH: metadata.outputs.path,
      SBOM_ASSET: metadata.outputs.asset, RUNNER_TEMP: dir, GITHUB_OUTPUT: output, SOURCE_DATE_EPOCH: "0"});
    const generate = () => {
      const result = spawnSync("bash", ["-e", "-o", "pipefail", "-c", shell("Generate and verify package SBOM")], {
        cwd: dir, env, encoding: "utf8",
      });
      assert.equal(result.status, 0, `${result.stderr}\n${result.stdout}`);
    };
    generate();
    const first = fs.readFileSync(path.join(dir, metadata.outputs.path));
    generate();
    assert.deepEqual(fs.readFileSync(path.join(dir, metadata.outputs.path)), first);
    const document = JSON.parse(first);
    assert.equal(document.metadata.component.name, "fixture");
    assert.equal(document.metadata.timestamp, "1970-01-01T00:00:00Z");
    assert.equal(document.components.find(p => p.name === "gleam_stdlib").scope, "required");
    assert.equal(document.components.find(p => p.name === "gleeunit").scope, "optional");
    console.log("native Trellis 1.3.0/licence_audit 0.15.0: JSON contracts, reproducibility, scopes and Hex inclusion passed");
  } finally {
    fs.rmSync(dir, {recursive: true, force: true});
  }
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
  await assert.rejects(run("select", {env: {SBOM_PACKAGE: "shelf"}}), /exact licence_audit_version/);
  for (const name of ["../shelf", "$(touch bad)", "Shelf"]) {
    await assert.rejects(run("select", {env: {SBOM_PACKAGE: name, LICENCE_AUDIT_VERSION: "0.15.0"}}), /root Hex/);
  }
  await assert.rejects(run("select", {mode: "git_only",
    env: {SBOM_PACKAGE: "shelf", LICENCE_AUDIT_VERSION: "0.15.0"}}), /hex\/mixed/);
  for (const version of ["latest", "v0.15.0", "0.15.0/other"]) {
    await assert.rejects(run("select", {env: {SBOM_PACKAGE: "shelf", LICENCE_AUDIT_VERSION: version}}), /exact/);
  }
  const packageList = {schema: "trellis.list/1", packages: [
    {name: "shelf", version: "1.0.0", path: ".", lifecycle: "hex", releasable: true}]};
  const ciOutputs = 'packages=["shelf"]\ntags=["custom-v1.0.0"]\nseries_tags=[]\n';
  const resolved = {schema: "trellis.ci_tag_package/1", name: "shelf", path: ".",
    version: "1.0.0", tag_kind: "exact", tag_version: "1.0.0"};
  const tagPackages = {"custom-v1.0.0": resolved};
  const metadata = await run("sbom-select", {packageList, ciOutputs, tagPackages,
    env: {SBOM_PACKAGE: "shelf", WORKING_DIRECTORY: "package with spaces"}});
  assert.deepEqual(metadata.outputs, {version: "1.0.0", tag: "custom-v1.0.0",
    path: "priv/shelf.cdx.json", asset: "custom-v1.0.0.cdx.json"});
  assert.deepEqual(metadata.commands, [["trellis", "list", "--releasable", "--json"],
    ["trellis", "ci", "outputs"], ["trellis", "ci", "tag-package", "custom-v1.0.0", "--json"]]);
  assert(metadata.commandEnvs.every(o => o.cwd === "package with spaces"));
  const multiple = await run("sbom-select", {packageList,
    ciOutputs: 'tags=["other-v2.0.0","custom-v1.0.0"]\n',
    tagPackages: {...tagPackages, "other-v2.0.0": {...resolved, name: "other", path: "packages/other",
      version: "2.0.0", tag_version: "2.0.0"}}, env: {SBOM_PACKAGE: "shelf"}});
  assert.deepEqual(multiple.outputs, metadata.outputs);
  await assert.rejects(run("sbom-select", {packageList, ciOutputs: 'tags=["first","second"]\n',
    tagPackages: {first: resolved, second: resolved}, env: {SBOM_PACKAGE: "shelf"}}), /one exact tag/);
  for (const change of [{path: "packages/shelf"}, {lifecycle: "git_only"}, {releasable: false},
    {version: "bad"}, {name: "other"}]) {
    await assert.rejects(run("sbom-select", {ciOutputs, tagPackages,
      packageList: {...packageList, packages: [{...packageList.packages[0], ...change}]},
      env: {SBOM_PACKAGE: "shelf"}}), /root|version/);
  }
  for (const facts of ["", "tags=[]\n", 'tags=["a"]\ntags=["b"]\n',
    'tags=["a","a"]\n', "tags={}\n", 'tags=[12]\n']) {
    await assert.rejects(run("sbom-select", {packageList, ciOutputs: facts, tagPackages,
      env: {SBOM_PACKAGE: "shelf"}}), /tags output|exact tag/);
  }
  for (const change of [{tag_kind: "series"}, {schema: "trellis.ci_tag_package/2"},
    {tag_version: "2.0.0"}, {version: "2.0.0"}, {path: "packages/shelf"}, {name: "other"}]) {
    await assert.rejects(run("sbom-select", {packageList, ciOutputs,
      tagPackages: {"custom-v1.0.0": {...resolved, ...change}}, env: {SBOM_PACKAGE: "shelf"}}), /exact tag/);
  }
  await assert.rejects(run("sbom-select", {packageList: {...packageList, schema: "trellis.list/2"},
    env: {SBOM_PACKAGE: "shelf"}}), /package contract/);
  await assert.rejects(run("sbom-select", {packageList, ciOutputs: 'tags=["shelf/v1.0.0"]\n',
    tagPackages: {"shelf/v1.0.0": resolved}, env: {SBOM_PACKAGE: "shelf"}}), /filename-safe/);
  await assert.rejects(run("sbom-select", {packageList, ciOutputs, tagPackages: {},
    env: {SBOM_PACKAGE: "shelf"}}), /resolver failed/);
  const sbomOutcomes = {SBOM_PACKAGE: "shelf", TAG_OUTCOME: "success", PUBLISH_OUTCOME: "success",
    GENERATE_SBOM_OUTCOME: "success", HEX_SBOM_OUTCOME: "success", RELEASE_SBOM_OUTCOME: "success"};
  assert.equal((await run("publication-outcome", {env: sbomOutcomes})).outputs.complete, "true");
  for (const key of ["GENERATE_SBOM_OUTCOME", "HEX_SBOM_OUTCOME", "RELEASE_SBOM_OUTCOME"]) {
    for (const outcome of ["failure", "skipped", "cancelled", ""]) {
      const failed = await run("publication-outcome", {env: {...sbomOutcomes, [key]: outcome}});
      assert.equal(failed.writes[0].state, "failure");
      assert(!failed.outputs.complete);
    }
  }
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
  sbomShellTests();
  await nativeTaggedRetryTests();
  await nativeSbomContractTests();
  for (const name of ["Select SBOM package and exact tag", "Install native licence_audit",
    "Generate and verify package SBOM", "Verify published Hex SBOM", "Reconcile GitHub Release SBOM"]) {
    assert(step(name).includes("if: steps.select.outputs.publish_sha != '' && inputs.sbom_package != ''"));
    assert(!step(name).includes("always()"), "Failure must skip subsequent SBOM/release work");
  }
  for (const name of ["Install native licence_audit", "Generate and verify package SBOM", "Verify published Hex SBOM"]) {
    assert(!step(name).includes("secrets.") && !step(name).includes("steps.app.") &&
      !step(name).includes("git_header"), "No publication or preparation secrets in SBOM tooling");
  }
  const ordered = ["Generate and verify package SBOM", "Publish Hex members", "Verify published Hex SBOM",
    "Tag approved release", "Reconcile GitHub Release SBOM", "Record publication outcome"];
  for (let i = 1; i < ordered.length; i++) {
    assert(workflow.indexOf(`- name: ${ordered[i-1]}`) < workflow.indexOf(`- name: ${ordered[i]}`));
  }
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
