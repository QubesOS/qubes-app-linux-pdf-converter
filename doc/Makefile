PANDOC=pandoc -s -f rst -t man

DOCS=$(patsubst %.rst,%.1.gz,$(wildcard *.rst))

help:
	@echo "make rst=example.rst preview	-- generate manpage preview from example.rst"
	@echo "make manpages			-- generate manpages"
	@echo "make install			-- generate manpages and copy them to /usr/share/man"

install: manpages
	install -d $(DESTDIR)/usr/share/man/man1
	install -D $(DOCS) $(DESTDIR)/usr/share/man/man1/

%.1: %.rst
	$(PANDOC) $< > $@

%.1.gz: %.1
	gzip -f $<

manpages: $(DOCS)

clean:
	rm -f $(DOCS)
