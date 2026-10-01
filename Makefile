.PHONY: run test demo
run:
	python3 -m propdesk serve
test:
	python3 -m unittest discover -s tests -v
demo:
	python3 -m propdesk demo --symbol EURUSD --output /tmp/prop-lab-demo.json
