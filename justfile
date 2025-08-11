#!/usr/bin/env -S just --justfile
# ^ A shebang isn't required, but allows a justfile to be executed
#   like a script, with `./justfile test`, for example.

alias t := test

log := "warn"

export JUST_LOG := log




# Local Variables:
# mode: makefile
# End:
# vim: set ft=make :