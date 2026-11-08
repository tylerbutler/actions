import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "_common"))
from gha import append_summary, write_output  # noqa: E402
from trellis import boolean, invoke, json_array, main, records  # noqa: E402

OUTPUTS = ("ok", "strictness", "has_entries", "needs_entry",
           "needs_entry_packages", "invalid_fragments", "preview")


def report(args: list[str]) -> subprocess.CompletedProcess[str]:
    try:
        return invoke(args)
    except OSError as error:
        print(f"::error::trellis could not start: {error}", file=sys.stderr)
        return subprocess.CompletedProcess(args, 127, "", str(error))


def check() -> None:
    changelog = boolean("CHECK_CHANGELOG", "true")
    if changelog and (not os.environ.get("BASE") or not os.environ.get("HEAD")):
        raise ValueError("base and head are required when check_changelog=true")
    doctor = report(["doctor", "--format", "github"])
    sys.stdout.write(doctor.stdout)
    append_summary(f"Doctor: {'passed' if doctor.returncode == 0 else 'failed'} (exit {doctor.returncode}).")
    errors = []
    result = None
    if changelog:
        result = report(["changelog", "check", "--base", os.environ["BASE"],
                         "--head", os.environ["HEAD"], "--format", "github"])
        try:
            outputs = records(result.stdout)
            for key in OUTPUTS:
                if key not in outputs:
                    raise ValueError(f"missing changelog output: {key}")
            for key in ("ok", "has_entries", "needs_entry"):
                if outputs[key] not in ("true", "false"):
                    raise ValueError(f"invalid changelog boolean: {key}")
            if outputs["strictness"] not in ("error", "warn", "off"):
                raise ValueError("invalid changelog strictness")
            for key in ("needs_entry_packages", "invalid_fragments"):
                json_array(outputs[key])
            for key in OUTPUTS:
                write_output(key, outputs[key])
            append_summary(outputs["preview"])
            if outputs["ok"] != "true":
                errors.append("changelog verdict failed")
        except (ValueError, KeyError) as error:
            errors.append(str(error))
        append_summary(f"Changelog: {'passed' if result.returncode == 0 and not errors else 'failed'} "
                       f"(exit {result.returncode}).")
    else:
        append_summary("Changelog: disabled.")
    if doctor.returncode or (result is not None and result.returncode):
        # Both reports are complete; prefer the first failing command's code.
        code = doctor.returncode or result.returncode
        raise subprocess.CalledProcessError(code, "trellis checks")
    if errors:
        raise ValueError("; ".join(errors))


if __name__ == "__main__":
    main("Trellis check", check)
