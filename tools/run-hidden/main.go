// Command run-hidden starts a console program on Windows without a console
// window and exits with the program's exit code.
//
// Windows scheduled tasks that run in the owner's logon session start it in
// place of powershell.exe: a console program that Task Scheduler starts
// directly opens a console window each time it runs. run-hidden is built for
// the Windows GUI subsystem (-H=windowsgui), so it has no console of its own,
// and it starts the program with CREATE_NO_WINDOW. Unlike `conhost.exe
// --headless`, it hands the exit code back, so the task's last result still
// says whether the program failed (docs/runbook/windows-host.md).
//
//	run-hidden.exe <program> [args...]
//
// Exit codes: the program's own; 2 without a program (and on every OS but
// Windows); 1 when the program cannot be started.
package main

import "os"

func main() {
	os.Exit(run(os.Args[1:]))
}
