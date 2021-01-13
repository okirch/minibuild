
LIBDIR ?= /usr/lib64
PYDIR	= $(LIBDIR)/python3.6/site-packages/minibuild
ETCDIR	= /etc
BINDIR	= /usr/bin

VERSION	= 0.0.1

CONFIG	= minibuild.json
CONTAINERS = \
	brcoti-python3 \
	brcoti-ruby25

ifdef RPM_OPT_FLAGS
CCOPT	= $(RPM_OPT_FLAGS)
else
#CCOPT	= -O2 -g
CCOPT	= -g
endif

all: marshal48.so bundler.so

install: marshal48.so bundler.so
	mkdir -p $(DESTDIR)$(PYDIR)
	install -m 555 -s marshal48.so $(DESTDIR)$(PYDIR)
	install -m 555 -s bundler.so $(DESTDIR)$(PYDIR)
	install -m 555 *.py $(DESTDIR)$(PYDIR)
	install -m 644 $(CONFIG) $(DESTDIR)$(ETCDIR)
	install -m 555 minibuild $(DESTDIR)$(BINDIR)

IMGDIR	= images
containers: $(addprefix $(IMGDIR)/,$(CONTAINERS))

$(IMGDIR)/brcoti-%: Dockerfile.%
	@mkdir -p $(IMGDIR)
	podman build --tag $(@F):$(VERSION) --tag $(@F):latest -f $<
	podman push $(@F) oci-archive:$@


CFLAGS	:= -fPIC $(CCOPT) \
	  -D_GNU_SOURCE \
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
	  ruby_instancedict.c \
	  ruby_trace.c \
	  unmarshal.c
MARSHAL_OBJS = $(addprefix marshal48/,$(patsubst %.c,%.o,$(MARSHAL_SRCS)))

marshal48.so: $(MARSHAL_OBJS)
	$(CC) --shared -o $@ $(MARSHAL_OBJS)

BUNDLER_SRCS = \
	extension.c \
	gemfile.c \
	parser.c
BUNDLER_OBJS = $(addprefix bundler/,$(patsubst %.c,%.o,$(BUNDLER_SRCS)))

bundler.so: $(BUNDLER_OBJS)
	$(CC) --shared -o $@ $(BUNDLER_OBJS)

clean:
	rm -f *.so marshal48/*.o bundler/*.o
