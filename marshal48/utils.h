/*
Ruby marshal48 - for python

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

#ifndef EXTENSION_UTILS_H
#define EXTENSION_UTILS_H

#include <Python.h>

typedef struct simple_object_array {
	unsigned int		count;
	PyObject **		items;
} simple_object_array_t;

extern void		simple_object_array_append(simple_object_array_t *array, PyObject *sym_obj);
extern PyObject *	simple_object_array_get(simple_object_array_t *array, unsigned int index);
extern void		simple_object_array_destroy(simple_object_array_t *array);

#endif /* EXTENSION_UTILS_H */
