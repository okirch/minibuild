/*
Ruby type system

Copyright (C) 2020 SUSE

This program is free software; you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, version 2.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License along
with this program; if not, write to the Free Software Foundation, Inc.,
51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA.
*/


#ifndef RUBY_H
#define RUBY_H

#include <Python.h>

typedef struct ruby_context	ruby_context_t;
typedef struct ruby_instance	ruby_instance_t;
typedef struct ruby_type	ruby_type_t;
typedef struct ruby_marshal	ruby_marshal_t;
typedef struct ruby_converter	ruby_converter_t;

/* anonymous decls for some structs */
struct ruby_byteseq;
typedef struct ruby_repr_context ruby_repr_context_t;

enum {
	RUBY_REG_EPHEMERAL,
	RUBY_REG_SYMBOL,
	RUBY_REG_OBJECT,
};

struct ruby_type {
	const char *	name;
	size_t		size;
	int		registration;
	ruby_type_t *	base_type;

	bool		(*marshal)(ruby_instance_t *, ruby_marshal_t *);
	ruby_instance_t *(*unmarshal)(ruby_marshal_t *);

	void		(*del)(ruby_instance_t *);
	const char *	(*repr)(ruby_instance_t *, ruby_repr_context_t *);
	bool		(*set_var)(ruby_instance_t *self, ruby_instance_t *key, ruby_instance_t *value);

	ruby_instance_t *(*get_cached)(ruby_converter_t *, PyObject *);
	void		(*add_cache)(ruby_instance_t *, ruby_converter_t *);

	bool		(*from_python)(ruby_instance_t *, PyObject *, ruby_converter_t *);
	PyObject *	(*to_python)(ruby_instance_t *, ruby_converter_t *);
};

struct ruby_instance {
	const ruby_type_t *op;

	struct {
		int	kind;
		int	id;
	} reg;
	int		marshal_id;

	PyObject *	native;
	unsigned int	hash_value;
};

struct ruby_converter {
	ruby_context_t *context;
	PyObject *	factory;
	struct ruby_instancedict *strings;
};

static inline void
ruby_instance_del(ruby_instance_t *self)
{
	self->op->del(self);
}

static inline bool
ruby_instance_set_var(ruby_instance_t *self, ruby_instance_t *key, ruby_instance_t *value)
{
	const ruby_type_t *op;

	for (op = self->op; op; op = op->base_type) {
		if (op->set_var)
			return op->set_var(self, key, value);
	}
	return false;

}

extern const ruby_instance_t	ruby_True;
extern const ruby_instance_t	ruby_False;
extern const ruby_instance_t	ruby_None;

extern ruby_type_t	ruby_Int_type;
extern ruby_type_t	ruby_Symbol_type;
extern ruby_type_t	ruby_Array_type;
extern ruby_type_t	ruby_String_type;
extern ruby_type_t	ruby_Hash_type;
extern ruby_type_t	ruby_GenericObject_type;
extern ruby_type_t	ruby_UserDefined_type;
extern ruby_type_t	ruby_UserMarshal_type;

extern ruby_context_t *	ruby_context_new(void);
extern void		ruby_context_free(ruby_context_t *);
extern ruby_instance_t *ruby_context_get_symbol(ruby_context_t *, unsigned int);
extern ruby_instance_t *ruby_context_get_object(ruby_context_t *, unsigned int);
extern ruby_instance_t *ruby_context_find_symbol(ruby_context_t *, const char *);


extern ruby_converter_t *ruby_converter_new(ruby_context_t *, PyObject *factory);
extern void		ruby_converter_free(ruby_converter_t *);

extern PyObject *	ruby_instance_to_python(ruby_instance_t *self, ruby_converter_t *converter);
extern ruby_instance_t *ruby_instance_from_python(PyObject *self, ruby_converter_t *converter);
extern const char *	ruby_instance_repr(ruby_instance_t *self);

extern bool		ruby_Bool_check(const ruby_instance_t *self);
extern bool		ruby_Bool_is_true(const ruby_instance_t *self);
extern bool		ruby_Bool_is_false(const ruby_instance_t *self);
extern bool		ruby_None_check(const ruby_instance_t *self);

extern ruby_instance_t *ruby_Symbol_new(ruby_context_t *ctx, const char *name);
extern bool		ruby_Symbol_check(const ruby_instance_t *self);
extern const char *	ruby_Symbol_get_name(const ruby_instance_t *self);

extern ruby_instance_t *ruby_Int_new(ruby_context_t *, long value);
extern bool		ruby_Int_check(const ruby_instance_t *self);
extern long		ruby_Int_get_value(const ruby_instance_t *self);

extern ruby_instance_t *ruby_String_new(ruby_context_t *, const char *);
extern bool		ruby_String_check(const ruby_instance_t *self);
extern const char *	ruby_String_get_value(const ruby_instance_t *self);

extern ruby_instance_t *ruby_Array_new(ruby_context_t *);
extern bool		ruby_Array_check(const ruby_instance_t *self);
extern bool		ruby_Array_append(const ruby_instance_t *self, ruby_instance_t *item);

extern ruby_instance_t *ruby_Hash_new(ruby_context_t *);
extern bool		ruby_Hash_check(const ruby_instance_t *self);
extern bool		ruby_Hash_add(const ruby_instance_t *self, ruby_instance_t *key, ruby_instance_t *value);

extern ruby_instance_t *ruby_GenericObject_new(ruby_context_t *, const char *classname);
extern bool		ruby_GenericObject_check(const ruby_instance_t *self);
extern ruby_instance_t *__ruby_GenericObject_new(ruby_context_t *, const char *classname, const ruby_type_t *type);
extern bool		__ruby_GenericObject_apply_vars(ruby_instance_t *self, PyObject *result, ruby_converter_t *);

extern ruby_instance_t *ruby_UserDefined_new(ruby_context_t *ctx, const char *classname);
extern bool		ruby_UserDefined_check(const ruby_instance_t *self);
extern bool		ruby_UserDefined_set_data(ruby_instance_t *self, const void *data, unsigned int count);
extern struct ruby_byteseq *__ruby_UserDefined_get_data_rw(ruby_instance_t *self);

extern ruby_instance_t *ruby_UserMarshal_new(ruby_context_t *ctx, const char *classname);
extern bool		ruby_UserMarshal_check(const ruby_instance_t *self);
extern bool		ruby_UserMarshal_set_data(ruby_instance_t *self, ruby_instance_t *data);

extern char *		ruby_instance_as_string(ruby_instance_t *self);

#endif /* RUBY_H */

