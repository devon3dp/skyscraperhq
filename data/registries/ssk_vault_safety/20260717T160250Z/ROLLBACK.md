# SSK Vault Rollback (20260717T160250Z)
The vault is fully additive under ONE dir: '/media/ross/SSK Cloud/SKYSCRAPERHQ/'.
To fully remove (non-destructive to all other data):
  ssh ross@192.168.1.23 "rm -rf '/media/ross/SSK Cloud/SKYSCRAPERHQ'"
Nothing else on the SSK was created/moved/renamed/deleted. Pre-existing folders
(brains, newbrains, models, kernal, core, fortress3, ... ) untouched.
Sync service (if installed): systemctl --user (Pi) disable+stop qsb-ssk-vault-sync.timer/.service
Safety record + tree checksums: this directory.
