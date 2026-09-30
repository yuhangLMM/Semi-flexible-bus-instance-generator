# SFPB instance generator

This package contains 20 SFPB input instances, ten Leuven instances and ten synthetic Random instances, and the Python code that generates them from the supplied inputs. The files under `instances/` are ready to inspect or use; the generators reproduce them exactly.

| Location | Contents |
| --- | --- |
| `instances/Leuven/` | Ten Leuven JSON instances |
| `instances/Random/` | Ten synthetic Random JSON instances |
| `inputs/Leuven/` | REQreate configuration, REQreate candidate request pool, and the stop-to-stop travel-time matrix from the same REQreate run |
| `inputs/Random_profiles/` | Structural profiles used to generate the Random instances; these are generator inputs, not additional study instances |
| `generators/` | The two instance generators, their shared REQreate mapping, and a reproduction check, all standard-library Python |
| `reqreate/` | Patch, package versions, and commands for rerunning the optional upstream REQreate step |
| `docs/INSTANCE_FORMAT.md` | Field definitions, units, and a checklist of the available information |
| `docs/GENERATION_METHOD.md` | The REQreate step, instance construction, and random seeds |
| `docs/INSTANCE_MANIFEST.csv` | One-row summary of every final instance |

## Recreate the instances

The generators need Python 3.8 or later and no additional packages. Run these commands from this folder:

```bash
python generators/generate_leuven_instances.py
python generators/generate_random_instances.py
python generators/check_reproduction.py
```

On macOS or Linux, use `python3` if `python` does not start Python 3. The scripts locate their inputs relative to their own location, so the commands also work from another folder.

The first two commands take a few seconds and write the instances to `generated/Leuven/` and `generated/Random/`. The third compares them with the packaged files and ends with `All 20 packaged instances were reproduced.` It compares JSON content, so line endings, which depend on the operating system, do not matter. With Python 3.8.1 and 3.12.14 on Windows, the regenerated files are byte-identical to the packaged ones.

Both generators accept `--output-dir` to write elsewhere. The Leuven generator overwrites existing output; the Random generator stops if its output already exists, unless `--force` is given. The Random generator's `--request-seed` option draws another demand realization on the same five networks.

## Instance files

Each packaged JSON file has five model-input sections: `config`, `network`, `fleet`, `requests`, and `parameters`. The Random files also have optional `generation` metadata describing their construction; this metadata does not enter the model input. See `docs/INSTANCE_FORMAT.md` for the exact fields.

The files describe a corridor service, vehicle supply, and passenger requests. They do not contain scheduled departure tables or realizations of congestion, passenger no-shows, or cancellations.

## REQreate

The Leuven candidate requests and travel times come from REQreate, an instance generator for demand-responsive transport (<https://github.com/michellqueiroz-ua/instance-generator>), run with local changes on commit `d50f41a0`. The generators read only the supplied outputs, so REQreate is not needed to recreate the instances. `docs/GENERATION_METHOD.md` describes the REQreate step, and `reqreate/README.md` explains how to repeat it.

## License

The code, documentation, and instances are released under the MIT License; see `LICENSE`. `reqreate/reqreate_local_changes.patch` modifies REQreate and contains portions of its code, which REQreate distributes under its own MIT License; see `reqreate/LICENSE-REQreate`.
