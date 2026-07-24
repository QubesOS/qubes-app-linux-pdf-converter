SPHINXBUILD   = sphinx-build
BUILDDIR      = _build/man

.PHONY: help
help:
	@echo "make manpages			-- generate manpages"
	@echo "make install			-- generate manpages and copy them to /usr/share/man"
	@echo "make clean 			-- remove generated manpages in build directory"

.PHONY: manpages
manpages:
	$(SPHINXBUILD) -b man . $(BUILDDIR)
	for file in $(BUILDDIR)/*.[12345678]; do \
		gzip -f $$file; \
	done
	@echo
	@echo "Build finished. The manual pages are in $(BUILDDIR)."

.PHONY: install
install: manpages
	install -d $(DESTDIR)/usr/share/man/man1
	install -D $(BUILDDIR)/* $(DESTDIR)/usr/share/man/man1/

.PHONY: clean
clean:
	rm -f $(BUILDDIR)
