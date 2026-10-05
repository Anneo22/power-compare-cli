<p align="left"><img src="docs/logo.svg" width="230" alt="Power Compare logo"></p>

# Power Compare

Compare cycling power recordings from FIT and CSV files, then choose the next test when the numbers disagree. Runs locally, with a command line for scripts and agents and a small browser interface.

[![Checks](https://github.com/Anneo22/power-compare-cli/actions/workflows/checks.yml/badge.svg)](https://github.com/Anneo22/power-compare-cli/actions/workflows/checks.yml)

Two meters can disagree because of their measurements, the recording devices, timestamps or trainer control. A graph alone does not tell you which one to test. Power Compare keeps those questions separate: inspect the raw samples, compare measured stages, and follow a short repeatable protocol.

## Start

Requires Python 3.10 or later. From a checkout:

```sh
python -m pip install .
power-compare serve
```

Open [localhost:8765](http://127.0.0.1:8765). Choose a reference recording, add the other files and enter any steady-stage windows. Files are processed on your computer; there is no account or remote analysis service.

## Compare recordings

```sh
power-compare compare trainer.fit crank.fit phone.csv \
  --window 60:180 --window 300:420 --out results/comparison
```

This writes a standalone HTML report and JSON. It refuses to overwrite existing files. Without `--out`, the command prints JSON only, which an agent or another script can inspect.

The first file is the reference. Windows are seconds after that recording starts, with an exclusive end. Positive differences mean the comparison reads higher. Use the final steady part of a stage; keep surges and recoveries separate. A whole-ride mean can hide a low-power error that changes at higher loads.

The report includes original-file hashes, source/clock information, paired-sample and elapsed-time coverage, mean differences in watts and percent, variability, unmatched zeros and a separate delay diagnostic. Missing samples are gaps; measured zeros stay in the calculation. An unmatched zero is a reason to inspect the ride, not proof of a failed sensor.

### Explicit clocks and power channels

```sh
power-compare compare trainer.fit headunit.fit \
  --offset headunit.fit=2 --window 60:180
```

A positive offset adds seconds to that file's timestamps. The report records your correction. It never applies a fitted delay to make the headline comparison agree. Delay estimates need enough overlapping, changing power; a flat stage cannot identify a delay reliably.

A FIT can contain native power and a second [Connect IQ](https://developer.garmin.com/connect-iq/overview/) developer channel. Select the field explicitly:

```sh
power-compare compare ride.fit ride.fit \
  --power-field 'ride.fit (2)=secondary_power' --window 60:180
```

`secondary_power` is an example field name. Check `available_power_fields` in the JSON and use the field actually present. Repeated filenames receive labels such as `ride.fit (2)`. No channel is silently substituted for native power.

CSV needs a header and either a timezone-aware ISO timestamp/Unix timestamp or elapsed seconds with an explicit start. Power must be numeric watts; cadence is optional. For example:

```csv
timestamp,power,cadence
2026-01-01T12:00:00Z,150,90
2026-01-01T12:00:01Z,152,91
```

For an elapsed-time export:

```sh
power-compare compare trainer.fit phone.csv \
  --start phone.csv=2026-01-01T12:00:00Z --window 60:180
```

## Choose a test

```sh
power-compare protocol --issue mismatch --controller computer \
  --meter trainer --meter crank
```

Other issues are `dropouts`, `lag` and `control`. The output gives a recording recipe, source checks and limits. Use one resistance controller, an independent power recording, stable settings and measured stages. Follow your meter manufacturer's zero-offset procedure; don't recalibrate or change sources halfway through a stage you intend to compare.

A successful zero offset does not have to change the watts. Closer agreement after a zero does not prove greater accuracy. Comparing receivers of the same meter checks the recording path; comparing independent meters checks their disagreement. Neither proves absolute calibration or validates FTP.

## Scope

This first release compares two to six files. It reads FIT with [fitdecode](https://github.com/polyvertex/fitdecode) and CSV with Python's standard library. It does not edit original recordings, pair sensors, control trainers or connect to Garmin accounts. Inputs should describe the same physical ride. Cadence helps interpret a change; gear, temperature and controller events still need your notes.

For an existing browser comparator, see [Compare the Watts](https://compare-the-watts.com/). For a complete training-analysis application, see [GoldenCheetah](https://www.goldencheetah.org/). Power Compare's focus is a reproducible diagnostic workflow and machine-readable results, rather than training plans or a calibration certificate.

To check the code:

```sh
python -m unittest discover -s tests -v
python scripts/check_examples.py
```

Apache License 2.0. See [LICENSE](LICENSE).

<p><a href="https://abcastor.com"><img src="docs/castor-footer.svg" width="350" alt="Chip, the Castor beaver, by Castor, we give a dam"></a></p>
