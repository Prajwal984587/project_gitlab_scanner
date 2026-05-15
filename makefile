.PHONY: help build run test clean docker-build docker-up docker-down

help:
	@echo "Available commands:"
	@echo "  make build      - Install dependencies"
	@echo "  make run        - Run development server"
	@echo "  make test       - Run tests"
	@echo "  make docker-build - Build Docker image"
	@echo "  make docker-up  - Start Docker containers"
	@echo "  make docker-down - Stop Docker containers"
	@echo "  make clean      - Clean cache files"

build:
	pip install -r requirements.txt
	python manage.py migrate

run:
	python manage.py runserver

test:
	python manage.py test scanner_app --verbosity=2

test-coverage:
	coverage run manage.py test scanner_app
	coverage report
	coverage html

docker-build:
	docker-compose build

docker-up:
	docker-compose up -d

docker-down:
	docker-compose down

docker-logs:
	docker-compose logs -f

clean:
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
	find . -type f -name "*.pyo" -delete
	find . -type f -name "*.db" -delete