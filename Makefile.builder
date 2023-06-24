ifeq ($(PACKAGE_SET),dom0)
  RPM_SPEC_FILES := rpm_spec/qpdf-converter-dom0.spec 
else ifeq ($(PACKAGE_SET),vm)
  # needs python 3.7+ - exclude stretch, jessie, centos[78], bionic, and xenial
  ifeq ($(filter $(DIST), stretch jessie centos7 centos8 centos-stream8 bionic xenial),)
    DEBIAN_BUILD_DIRS := debian
    RPM_SPEC_FILES := rpm_spec/qpdf-converter.spec
    ARCH_BUILD_DIRS := archlinux
  endif
endif

# Support for new packaging
ifneq ($(filter $(DISTRIBUTION), archlinux),)
    VERSION := $(file <$(ORIG_SRC)/$(DIST_SRC)/version)
    GIT_TARBALL_NAME ?= qubes-pdf-converter-$(VERSION)-1.tar.gz
    SOURCE_COPY_IN := source-archlinux-copy-in

source-archlinux-copy-in: PKGBUILD = $(CHROOT_DIR)/$(DIST_SRC)/$(ARCH_BUILD_DIRS)/PKGBUILD
source-archlinux-copy-in:
	cp $(PKGBUILD).in $(CHROOT_DIR)/$(DIST_SRC)/PKGBUILD
	sed -i "s/@VERSION@/$(VERSION)/g" $(CHROOT_DIR)/$(DIST_SRC)/PKGBUILD
	sed -i "s/@REL@/1/g" $(CHROOT_DIR)/$(DIST_SRC)/PKGBUILD
endif

# vim: filetype=make
