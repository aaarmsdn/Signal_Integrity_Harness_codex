# Generated Data Cache

This directory is a local generated-data cache for graph retrieval and source
registration outputs.

The shared repository keeps only this README and `.gitkeep`. Generated files
such as `sources.json`, `knowledge_graph.json`, raw inventories, Docling
registries, book chunks, and lint reports are intentionally ignored by Git.
They should be rebuilt on each machine or per case with commands such as:

```powershell
npm run register:raw-sources
npm run register:docling
npm run build:graph
npm run lint:wiki
```

Do not place copyrighted specs, books, proprietary datasets, or case evidence
here for sharing. Source documents belong in ignored raw/case-local folders,
and extracted evidence belongs in case-local `outputs/<case>/`.
