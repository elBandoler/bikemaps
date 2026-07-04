GEOJSON ?= roads.geojson
OUT ?= graph.json
PORT ?= 8000

.PHONY: help graph serve clean

help:
	@echo "make graph  - (re)build $(OUT) from $(GEOJSON) via osmnx (needs internet)"
	@echo "make serve  - serve the app at http://localhost:$(PORT)"
	@echo "make clean  - remove generated graph.json"

graph:
	python build_graph.py $(GEOJSON) -o $(OUT)

serve:
	@echo "Serving on http://localhost:$(PORT)  (Ctrl+C to stop)"
	python -m http.server $(PORT)

clean:
	rm -f $(OUT)
