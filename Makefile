.PHONY: run test demo
run:
	python3 -m propdesk serve
test:
	python3 scripts/test_offline.py
demo:
	python3 -m propdesk demo --symbol EURUSD --output /tmp/prop-lab-demo.json
