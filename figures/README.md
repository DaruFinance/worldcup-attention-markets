# figures

`make_figures.py` renders the publication figures as vector PDFs from the result CSVs in
`analysis/out/`: the attention spike against the flat aggregate response, the during-match
volume by market group against the prior literature's reported decline, the kickoff event
study, the comovement composition artifact, and the home-market estimates. Run the analysis
scripts first so the input CSVs exist.

```
python3 figures/make_figures.py
```
