
TAG	= 0.0.1

containers-python:
	podman build --tag brcoti-python3 -f Dockerfile.python
	podman push brcoti-python3 oci-archive:brcoti-python3:$(TAG)
