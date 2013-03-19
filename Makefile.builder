ifeq ($(PACKAGE_SET),dom0)
RPM_SPEC_FILES := rpm_spec/qpdf-converter-dom0.spec 
else ifeq ($(PACKAGE_SET),vm)
RPM_SPEC_FILES := rpm_spec/qpdf-converter.spec
endif
