# OS-specific details: host platform, shell, filesystem
# tools, packaging primitives, and venv PATH export.

ifeq ($(OS),Windows_NT)
  HOST_OS   := windows
  HOST_ARCH := $(if $(filter ARM64,$(PROCESSOR_ARCHITECTURE)),arm64,x64)
  OSARCH    := $(HOST_OS)-$(HOST_ARCH)

  SHELL := cmd.exe
  .SHELLFLAGS := /C

  RM    = del /q /f $(subst /,\,$1)
  RMDIR = rmdir /s /q $(subst /,\,$1)
  MKDIR = mkdir $(subst /,\,$1)
  CP    = copy /y $(subst /,\,$1) $(subst /,\,$2)
  CPDIR = xcopy /e /i /q /y $(subst /,\,$1) $(subst /,\,$2)

  EXE   := .exe
  ICON  := src/ui/public/icons/app.ico
  APP   := backpack$(EXE)

  export PATH := .venv/Scripts;bin/node_modules/.bin;$(PATH)
else
  HOST_OS := $(strip $(patsubst Darwin,macos,\
    $(patsubst Linux,linux,$(shell uname -s))))
  HOST_ARCH := $(strip $(patsubst x86_64,x64,\
    $(patsubst aarch64,arm64,$(shell uname -m))))
  OSARCH    := $(HOST_OS)-$(HOST_ARCH)

  RM    = rm -f $1
  RMDIR = rm -rf $1
  MKDIR = mkdir -p $1
  CP    = cp $1 $2
  CPDIR = cp -r $1 $2

  EXE   :=
  ICON  := src/ui/public/icons/app.$(if $(filter macos,$(HOST_OS)),icns,png)
  APP   := backpack

  export PATH := .venv/bin:bin/node_modules/.bin:$(PATH)
endif
