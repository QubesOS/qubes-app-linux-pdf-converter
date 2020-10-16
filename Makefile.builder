ifeq ($(PACKAGE_SET),dom0)
  RPM_SPEC_FILES := rpm_spec/qpdf-converter-dom0.spec 
else ifeq ($(PACKAGE_SET),vm)
  # needs python 3.7+ - exclude stretch, jessie, and centos7
  ifeq ($(filter $(DIST), stretch jessie centos7),)
    DEBIAN_BUILD_DIRS := debian
    RPM_SPEC_FILES := rpm_spec/qpdf-converter.spec
  endif
endif

# vim: filetype=make
