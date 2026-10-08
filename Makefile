.PHONY: seed test eval serve
seed:
	PYTHONPATH=src python3 -m nexusiq seed

test:
	PYTHONPATH=src python3 -m unittest discover -s tests -v

eval:
	PYTHONPATH=src python3 -m nexusiq evaluate

serve:
	PYTHONPATH=src python3 -m nexusiq serve
