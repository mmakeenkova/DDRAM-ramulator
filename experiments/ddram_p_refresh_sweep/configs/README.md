# Experiment configuration files

Pass a file's stem to `run.py --config`, or pass a path to a JSON file outside
this directory. A configuration supports these fields:

| Field | Meaning |
| --- | --- |
| `name` | Stable experiment identifier and default output-directory name |
| `description` | Human-readable description copied into `results.json` |
| `trace_root` | Optional MORDOR trace directory; the environment/default is used when omitted |
| `workloads` | Trace filenames to simulate |
| `instructions` | Instructions retired by SimpleO3 in each simulation |
| `trace_lines` | Maximum source records copied into the bounded local input |
| `refresh_mode` | `Oracle` or `Nack` |
| `refresh_interval` | Internal-refresh interval, or `-1` for `nREFI` |
| `refresh_duration` | Internal-refresh duration, or `-1` for `nRFCsb` |
| `workers` | Number of simulations to run concurrently |

Each sweep runs the matched one-view/two-view and refresh-off/refresh-on matrix.
Command-line options override fields after loading. For a meaningful variant,
give it a new `name` or pass a distinct `--output-dir`; this prevents the
result from replacing the original named study.
