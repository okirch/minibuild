/*
Ruby object system

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


#ifndef RUBY_IMPL_H
#define RUBY_IMPL_H


#include <Python.h>
#include <string.h>
#include <stdbool.h>

typedef struct ruby_context ruby_context_t;
typedef struct ruby_instance ruby_instance_t;
typedef struct ruby_type ruby_type_t;

#include "ruby_utils.h"

typedef void		(*ruby_instance_del_fn_t)(ruby_instance_t *);
typedef ruby_instance_t *(*ruby_instance_unmarshal_fn_t)(ruby_unmarshal_t *);
typedef const char *	(*ruby_instance_repr_fn_t)(ruby_instance_t *);
typedef bool		(*ruby_instance_set_var_fn_t)(ruby_instance_t *, ruby_instance_t *, ruby_instance_t *);
typedef PyObject *	(*ruby_instance_convert_fn_t)(ruby_instance_t *);

extern bool		__ruby_instance_check_type(const ruby_instance_t *self, const ruby_type_t *type);
extern ruby_instance_t *__ruby_instance_new(ruby_context_t *, const ruby_type_t *);
extern void		__ruby_instance_del(ruby_instance_t *self);

extern unsigned int	ruby_context_register_symbol(ruby_context_t *, ruby_instance_t *);
extern unsigned int	ruby_context_register_object(ruby_context_t *, ruby_instance_t *);
extern unsigned int	ruby_context_register_ephemeral(ruby_context_t *, ruby_instance_t *);

/* This type needs to be declared here so that UserDefined and UserMarshal can derive from it */
typedef struct {
	ruby_instance_t	obj_base;
	char *		obj_classname;
	ruby_dict_t	obj_vars;
} ruby_GenericObject;


#endif /* RUBY_IMPL_H */

