
TAG	= 0.0.1

all: containers-python containers-ruby

containers-python:
	podman build --tag brcoti-python3 -f Dockerfile.python
	podman push brcoti-python3 oci-archive:brcoti-python3:$(TAG)

containers-ruby:
	podman build --tag brcoti-ruby25 -f Dockerfile.ruby25
	podman push brcoti-ruby25 oci-archive:brcoti-ruby25:$(TAG)
