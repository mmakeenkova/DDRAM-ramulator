LATEX := pdflatex
LATEXFLAGS := -interaction=nonstopmode -halt-on-error
DOCUMENTS := ddram_o_milestone1

.PHONY: all clean

all: $(DOCUMENTS:%=%.pdf)

%.pdf: %.tex
	$(LATEX) $(LATEXFLAGS) $<
	$(LATEX) $(LATEXFLAGS) $<
	$(LATEX) $(LATEXFLAGS) $<

clean:
	rm -f $(DOCUMENTS:%=%.aux) $(DOCUMENTS:%=%.log) \
	      $(DOCUMENTS:%=%.out) $(DOCUMENTS:%=%.toc)
