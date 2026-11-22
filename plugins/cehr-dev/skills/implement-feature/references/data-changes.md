# Changes that touch data

Read this when a change touches datasets, tokenization or caches. These fill a disk
quickly: a tokenized dataset can be many times the size of its source, each processing
pass can add a cache of the same size, and stale copies are cleaned up by hand.

## Do not grow the data on disk

A data change must not add to what is stored.

- Each `dataset.map`, `filter` or similar call can write a cache as large as its input.
  Before adding one, look for a prepared dataset or cache that already holds what the
  feature needs and read from that.
- Do not write a second version of a dataset to carry one more field.
- If making an existing data utility faster or leaner would serve the feature and the
  steps after it, do that in preference to a new pass over the data.
- Moving work from a stored pass to load time, such as a collator or a transform, saves
  storage but can slow training. Benchmark the loading speed before and after, and give
  the numbers in the report.
- Say in the report which caches the change creates or leaves unused. Do not delete them.

## Keep the hash that identifies a dataset stable

Processes find a tokenized dataset or a cache by a hash of what produced it: paths,
settings, the mapping object. When that hash changes, every existing dataset becomes
unreachable and is rebuilt beside the old one, which is the storage problem again.

- Before changing anything near it, find what feeds the hash: the fields of a path hash,
  and for `dataset.map` the pickled state of the function or object it is given.
- A new option leaves the hash unchanged at its default value. A new field in a hashed
  config, a new attribute on a mapping object, or a renamed class changes it for every
  existing dataset.
- Change the hash only when the stored data really differs, and then on purpose: say so
  in the plan, with what will have to be rebuilt.
- Prefer an explicit key, built from only the inputs that change the output and carrying
  a version to bump deliberately, over hashing a whole object.
