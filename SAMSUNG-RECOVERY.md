# Samsung testing: test1 versus test2

**test1** introduced a manual h8q-only firmware recovery with an explicit opt-in.
Installing it alone did not request a reload. The report that its UI still
failed after five seconds did not establish whether recovery actually ran.

**test2** replaces the model-selected primary paths with a common AIDL bridge.
Pixel is no longer preferred. It mounts library/config files into init's
namespace, identifies the factory owner and its init service, and uses an audited
firmware stop/start handler once after the existing ten-second late-load delay.
The old opt-in marker is not required; the disable marker is still respected.
The historical model-specific recovery scripts remain in source for reference,
but are not in the test2 ZIP or called by its dispatcher.

Read [the common late-load guide](TEMP-ROOT-RELOAD.md) for exact behavior,
disable/retry controls, status meanings, limits and recovery risks. This is an
experimental candidate, not a Samsung compatibility claim. No current Samsung
library load, effect registration or processed audio has been demonstrated.

The signed root app 1.6.17/code 62, native V4 driver and matching `jdspctl` are
unchanged from beta-4. A new native build is not being disguised as a script fix.
