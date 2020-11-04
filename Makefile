
VERSION	= 0.0.1
IMGDIR	= images

CONTAINERS = \
	brcoti-python3 \
	brcoti-ruby25

all: $(addprefix $(IMGDIR)/,$(CONTAINERS))

$(IMGDIR)/brcoti-%: Dockerfile.%
	@mkdir -p $(IMGDIR)
	podman build --tag $(@F):$(VERSION) -f $<
	podman push $(@F) oci-archive:$@
