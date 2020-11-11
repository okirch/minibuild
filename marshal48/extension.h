/*
Ruby Marshal48 machine - for python

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


#ifndef MARSHAL48_PYTHON_EXT_H
#define MARSHAL48_PYTHON_EXT_H


#include <Python.h>
#include <string.h>
#include <stdbool.h>

typedef struct ruby_context ruby_context_t;
typedef struct ruby_instance ruby_instance_t;
typedef struct ruby_type ruby_type_t;

/* utility types */
typedef struct ruby_array	ruby_array_t;
typedef struct ruby_byteseq	ruby_byteseq_t;
typedef struct ruby_dict	ruby_dict_t;

extern ruby_context_t *	ruby_context_new(void);
extern void		ruby_context_free(ruby_context_t *);

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

	void		(*del)(ruby_instance_t *);
	const char *	(*repr)(ruby_instance_t *);
	bool		(*set_var)(ruby_instance_t *self, ruby_instance_t *key, ruby_instance_t *value);
	PyObject *	(*convert)(ruby_instance_t *);
};

struct ruby_instance {
	const ruby_type_t *op;

	struct {
		int	kind;
		int	id;
	} reg;

	PyObject *	native;
};

static inline void
ruby_instance_del(ruby_instance_t *self)
{
	self->op->del(self);
}

static inline const char *
ruby_instance_repr(ruby_instance_t *self)
{
	return self->op->repr(self);
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

static inline PyObject *
ruby_instance_convert(ruby_instance_t *self)
{
	if (self->native == NULL) {
		self->native = self->op->convert(self);
		if (self->native == NULL)
			return NULL;
	}

	Py_INCREF(self->native);
	return self->native;
}


extern ruby_context_t *	ruby_context_new(void);
extern void		ruby_context_free(ruby_context_t *);

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
extern bool		__ruby_GenericObject_apply_vars(ruby_instance_t *self, PyObject *result);

extern ruby_instance_t *ruby_UserDefined_new(ruby_context_t *ctx, const char *classname);
extern bool		ruby_UserDefined_check(const ruby_instance_t *self);
extern bool		ruby_UserDefined_set_data(ruby_instance_t *self, const void *data, unsigned int count);
extern ruby_byteseq_t *	__ruby_UserDefined_get_data_rw(ruby_instance_t *self);

extern ruby_instance_t *ruby_UserMarshal_new(ruby_context_t *ctx, const char *classname);
extern bool		ruby_UserMarshal_check(const ruby_instance_t *self);
extern bool		ruby_UserMarshal_set_data(ruby_instance_t *self, ruby_instance_t *data);

extern char *		ruby_instance_as_string(ruby_instance_t *self);

extern ruby_instance_t *marshal48_unmarshal_io(ruby_context_t *ruby, PyObject *io);
extern PyObject *	marshal48_instantiate_ruby_type(const char *name);
extern PyObject *	marshal48_instantiate_ruby_type_with_arg(const char *name, PyObject *);


static inline void
assign_string(char **var, char *str)
{
	if (*var == str)
		return;
	if (str)
		str = strdup(str);
	if (*var)
		free(*var);
	*var = str;
}

static inline PyObject *
return_string_or_none(const char *value)
{
	if (value == NULL) {
		Py_INCREF(Py_None);
		return Py_None;
	}
	return PyUnicode_FromString(value);
}

static inline PyObject *
return_bool(bool bv)
{
	PyObject *result;

	result = bv? Py_True : Py_False;
	Py_INCREF(result);
	return result;
}

static inline void
drop_string(char **var)
{
	assign_string(var, NULL);
}

static inline void
assign_object(PyObject **var, PyObject *obj)
{
	if (obj) {
		Py_INCREF(obj);
	}
	if (*var) {
		Py_DECREF(*var);
	}
	*var = obj;
}

static inline void
drop_object(PyObject **var)
{
	assign_object(var, NULL);
}

#endif /* MARSHAL48_PYTHON_EXT_H */

