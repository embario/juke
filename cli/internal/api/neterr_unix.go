//go:build !windows

package api

import (
	"errors"
	"syscall"
)

func isRefusedSyscall(err error) bool {
	return errors.Is(err, syscall.ECONNREFUSED)
}

func isResetSyscall(err error) bool {
	return errors.Is(err, syscall.ECONNRESET)
}
