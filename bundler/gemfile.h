/*
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

#ifndef GEMFILE_H
#define GEMFILE_H

typedef struct bundler_context		bundler_context_t;

#define STRING_ARRAY_MAX		16
typedef struct {
	unsigned int			count;
	char *				value[STRING_ARRAY_MAX];
} string_array_t;

enum {
	VALUE_T_BOOL,
	VALUE_T_SYMBOL,
	VALUE_T_STRING,
	VALUE_T_INTEGER,
	VALUE_T_ARRAY,
};

typedef struct bundler_value  bundler_value_t;

#define VALUE_ARRAY_MAX			64
typedef struct {
	unsigned int			count;
	bundler_value_t *		value[VALUE_ARRAY_MAX];
} bundler_value_array_t;


struct bundler_value {
	int				type;
	union {
		bool			boolean;
		char *			string;
		char *			symbol;
		long			integer;
		bundler_value_array_t	array;
	};
};

typedef struct {
	char *				name;
	bundler_value_t *		value;
} bundler_ivar_t;

#define BUNDLER_IVAR_ARRAY_MAX		16
typedef struct {
	unsigned int			count;
	bundler_ivar_t			value[BUNDLER_IVAR_ARRAY_MAX];
} bundler_ivar_array_t;

typedef struct {
	bundler_ivar_array_t		ivars;
} bundler_object_instance_t;

typedef struct {
	bundler_object_instance_t	base;

	char *				name;
	string_array_t			dependency;

	bool				ignore;
} bundler_gem_t;

#define BUNDLER_GEM_ARRAY_MAX		64
typedef struct {
	unsigned int			count;
	bundler_gem_t			value[BUNDLER_GEM_ARRAY_MAX];
} bundler_gem_array_t;

#define BUNDLER_GEMFILE_MAX_GROUPS	16
typedef struct {
	char *				source;
	bundler_gem_array_t		gems;
} bundler_gemfile_t;

extern bundler_context_t *bundler_context_new(const char *ruby_version);
extern void		bundler_context_free(bundler_context_t *);
extern void		bundler_context_with_group(bundler_context_t *, const char *);
extern void		bundler_context_without_group(bundler_context_t *, const char *);

extern bundler_gemfile_t *bundler_gemfile_parse(const char *path, bundler_context_t *, char **error_msg_p);
extern void		bundler_gemfile_set_source(bundler_gemfile_t *gemf, const char *value);
extern void		bundler_gemfile_add_gemspec(bundler_gemfile_t *gemf);
extern void		bundler_gemfile_free(bundler_gemfile_t *);
extern bundler_gem_t *	bundler_gemfile_add_gem(bundler_gemfile_t *);
extern const char *	bundler_value_print(const bundler_value_t *v);
extern void		bundler_value_release(bundler_value_t *v);

extern const char *	string_array_print(const string_array_t *array);

#endif /* GEMFILE_H */
