//go:build !windows

package ipc_test

import "syscall"

// createStaleSocket creates a Unix domain socket at path using the raw syscall
// layer, then closes only the file descriptor. Unlike net.Listen + Close, this
// leaves the socket file on disk, simulating what happens when a daemon is
// killed with SIGKILL (kill -9).
func createStaleSocket(path string) error {
	fd, err := syscall.Socket(syscall.AF_UNIX, syscall.SOCK_STREAM, 0)
	if err != nil {
		return err
	}
	if err := syscall.Bind(fd, &syscall.SockaddrUnix{Name: path}); err != nil {
		_ = syscall.Close(fd)
		return err
	}
	// Close the FD; the socket file remains on disk.
	return syscall.Close(fd)
}
