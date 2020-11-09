
ifdef RPM_OPT_FLAGS
CCOPT	= $(RPM_OPT_FLAGS)
else
CCOPT	= -Wall -O2 -g
endif

CFLAGS	:= -fPIC $(CCOPT) \
	  -Werror \
	  $(shell python3-config --includes)
LDFLAGS	:= \
	  $(shell python3-config --libs)

LIBDIR ?= /usr/lib64
PYDIR	= $(LIBDIR)/python3.6/site-packages

OBJS	= extension.o \
	  ruby_symbol.o \
	  ruby_int.o \
	  ruby_string.o \
	  ruby_array.o \
	  ruby_hash.o \
	  ruby_object.o \
	  ruby_userdefined.o \
	  ruby_usermarshal.o \
	  unmarshal.o \
	  utils.o

all: marshal48.so

marshal48.so: $(OBJS)
	$(CC) --shared -o $@ $(OBJS)

clean:
	rm -f *.o *.so

install:
	mkdir -p $(DESTDIR)$(PYDIR)
	cp marshal48.so $(DESTDIR)$(PYDIR)
