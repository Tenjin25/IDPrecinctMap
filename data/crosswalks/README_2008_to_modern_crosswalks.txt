Idaho 2008-to-modern crosswalk outputs

Files without the "_nhgis" suffix:
- Built from direct geometric overlap between 2008 tabblock00 / vtd00 geography and the listed modern Idaho layers.
- These are the safest files to use for precinct-level carryover inside index.html because their vtd00 weights sum as expected by source precinct.

Files with the "_nhgis" suffix:
- Built by chaining NHGIS block crosswalks:
  - blk2000 -> blk2010
  - blk2010 -> blk2020
- Then assigning 2020 blocks to the modern Idaho layers.
- These are the better "atomic" research files for RDH/DRA-style block bridge work.

Files with the "_nhgis_popweighted" suffix:
- Built from the same NHGIS block chain, but now joined to Idaho Census 2000 block counts from Census 2000 SF1.
- `area_weight` in these compatibility CSVs is the effective precinct carryover weight used by the atlas.
- In the current Idaho outputs, every precinct compatibility row is population-weighted.

Recommended use:
- For research and auditing: use the detailed `_nhgis.csv` block- and vtd-level files.
- For atlas district carryover: use the `_nhgis_popweighted.csv` precinct compatibility files.

Historical note:
- Earlier NHGIS-named precinct compatibility CSVs without the `_popweighted` suffix were scratch output from before the 2000 block counts were attached.
- Treat those earlier files as superseded.
