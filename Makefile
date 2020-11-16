
VERSION	= 0.0.1
IMGDIR	= images

CONTAINERS = \
	brcoti-python3 \
	brcoti-ruby25

ifdef RPM_OPT_FLAGS
CCOPT	= $(RPM_OPT_FLAGS)
else
#CCOPT	= -O2 -g
CCOPT	= -g
endif

LIBDIR ?= /usr/lib64
PYDIR	= $(LIBDIR)/python3.6/site-packages

all: marshal48.so

install: marshal48.so
	mkdir -p $(DESTDIR)$(PYDIR)
	cp marshal48.so $(DESTDIR)$(PYDIR)

containers: $(addprefix $(IMGDIR)/,$(CONTAINERS))

$(IMGDIR)/brcoti-%: Dockerfile.%
	@mkdir -p $(IMGDIR)
	podman build --tag $(@F):$(VERSION) -f $<
	podman push $(@F) oci-archive:$@


CFLAGS	:= -fPIC $(CCOPT) \
	  -Wall -Werror \
	  $(shell python3-config --includes)
LDFLAGS	:= \
	  $(shell python3-config --libs)

MARSHAL_SRCS = \
	  extension.c \
	  ruby_symbol.c \
	  ruby_int.c \
	  ruby_string.c \
	  ruby_array.c \
	  ruby_hash.c \
	  ruby_object.c \
	  ruby_userdefined.c \
	  ruby_usermarshal.c \
	  ruby_base.c \
	  ruby_repr.c \
	  ruby_reader.c \
	  ruby_utils.c \
	  ruby_trace.c \
	  unmarshal.c
MARSHAL_OBJS = $(addprefix marshal48/,$(patsubst %.c,%.o,$(MARSHAL_SRCS)))

marshal48.so: $(MARSHAL_OBJS)
	$(CC) --shared -o $@ $(MARSHAL_OBJS)

clean:
	rm -f *.so marshal48/*.o
