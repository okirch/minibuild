/*
This file implements a fairly rubymentary gemfile parser.

It does not even try to parse anything that's slightly more advanced...
that is good enough for many Gemfiles, but there are some that this
code will choke on, like the ones in

farady
	(which has a complex expression assigning a dict to a temporary variable)


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

#include <libgen.h>	// for dirname

#include "extension.h"
#include "gemfile.h"


/* These are local to this file. */
struct bundler_context {
	char *		ruby_version;
	string_array_t	platforms;

	string_array_t	with_groups;
	string_array_t	without_groups;
};

static void		bundler_gem_destroy(bundler_gem_t *gem);

extern bundler_context_t *bundler_context_new(const char *ruby_version);
static void		bundler_context_set_ruby_version(bundler_context_t *, const char *);
static bool		bundler_context_match_platform(bundler_context_t *, const string_array_t *);
static bool		bundler_context_match_group(bundler_context_t *, const string_array_t *);
extern void		bundler_context_free(bundler_context_t *);

#if 0
static void *
bundler_parse_error(char **bufp, const char *fmt, ...)
{
	static char msgbuf[1024];
	va_list ap;

	va_start(ap, fmt);
	vsnprintf(msgbuf, sizeof(msgbuf), fmt, ap);
	va_end(ap);

	*bufp = msgbuf;
	return NULL;
}
#endif

enum {
	GEMFILE_T_ERROR = -1,
	GEMFILE_T_EOF = 0,
	GEMFILE_T_EOL,
	GEMFILE_T_IDENTIFIER,
	GEMFILE_T_SYMBOL,
	GEMFILE_T_STRING,
	GEMFILE_T_COMMA,
	GEMFILE_T_OPERATOR,
	GEMFILE_T_LBLOCKY,
	GEMFILE_T_RBLOCKY,
	GEMFILE_T_LBRACKET,
	GEMFILE_T_RBRACKET,
	GEMFILE_T_COLON,
	GEMFILE_T_PERCENT,

	__GEMFILE_T_MAX
};

static const char *	__gemfile_parser_token_names[__GEMFILE_T_MAX] = {
	[GEMFILE_T_EOF]			= "EOF",
        [GEMFILE_T_EOL]			= "EOL",
        [GEMFILE_T_IDENTIFIER]		= "IDENTIFIER",
        [GEMFILE_T_SYMBOL]		= "SYMBOL",
        [GEMFILE_T_STRING]		= "STRING",
        [GEMFILE_T_COMMA]		= "COMMA",
        [GEMFILE_T_OPERATOR]		= "OPERATOR",
        [GEMFILE_T_LBLOCKY]		= "LBLOCKY",
        [GEMFILE_T_RBLOCKY]		= "RBLOCKY",
        [GEMFILE_T_LBRACKET]		= "LBRACKET",
        [GEMFILE_T_RBRACKET]		= "RBRACKET",
        [GEMFILE_T_COLON]		= "COLON",
        [GEMFILE_T_PERCENT]		= "PERCENT",
};

typedef struct {
	const char *	filename;
	FILE *		file;
	unsigned int	lineno;
	bundler_context_t *bundler_ctx;

	char		linebuf[1024];
	char *		next;

	int		next_token;
	char		token_value[1024];

	bool		debug;

	/* Set while parsing arrays etc */
	unsigned int	ignore_eol;

	/* identation when printing debug msgs */
	unsigned int	nesting;

	/* Set to false if we're inside a block that should not
	 * get executed (eg if/else, or non-matching group/platform block */
	bool		execute;
} gemfile_parser_state;

struct block_context;

static inline bool
__gemfile_parser_at_eol(gemfile_parser_state *ps)
{
	return ps->next && *(ps->next) == '\0';
}

static unsigned int	gemfile_parser_skip_whitespace(gemfile_parser_state *ps);
static const char *	gemfile_parser_token_name(int token);
static int		gemfile_parser_single_token(gemfile_parser_state *ps);
static bundler_value_t *gemfile_parser_process_expression(gemfile_parser_state *ps);
static bool		gemfile_parser_err_unexpected_eol(gemfile_parser_state *ps);

typedef bool		__gemfile_parser_statement_handler_t(bundler_gemfile_t *gemf,
				gemfile_parser_state *ps, const char *identifier);

static bool		gemfile_parser_process_do_block(bundler_gemfile_t *gemf, gemfile_parser_state *ps);
static bool		__bundler_gemfile_eval(bundler_gemfile_t *gemf, const char *path,
				bundler_context_t *ctx, unsigned int nesting);

static void
gemfile_parser_init(gemfile_parser_state *ps, const char *filename, FILE *fp, bundler_context_t *ctx)
{
	memset(ps, 0, sizeof(*ps));
	ps->filename = filename;
	ps->file = fp;
	ps->next_token = -1;
	ps->bundler_ctx = ctx;
}

static void
gemfile_parser_destroy(gemfile_parser_state *ps)
{
	fclose(ps->file);
}

static void
gemfile_parser_debug(gemfile_parser_state *ps, const char *fmt, ...)
{
	va_list ap;

	if (!ps->debug)
		return;

	if (ps->nesting)
		fprintf(stderr, "%*.*s", ps->nesting, ps->nesting, "");
	va_start(ap, fmt);
	vfprintf(stderr, fmt, ap);
	va_end(ap);
}

static void
gemfile_parser_error(gemfile_parser_state *ps, const char *fmt, ...)
{
	va_list ap;

	fprintf(stderr, "Error at line %u\n", ps->lineno);

	va_start(ap, fmt);
	vfprintf(stderr, fmt, ap);
	va_end(ap);

	if (ps->linebuf[0]) {
		unsigned int len, max_len;

		if (ps->next == NULL)
			len = sizeof(ps->linebuf);
		else
			len = ps->next - ps->linebuf;

		max_len = strlen(ps->linebuf);
		if (len > max_len)
			len = max_len;

		fprintf(stderr, "%s\n", ps->linebuf);
		fprintf(stderr, "%*.*s^--- here\n",
				len, len,
				"");
	}
}

static int
gemfile_parser_next_token(gemfile_parser_state *ps, char **value_p)
{
	int token;
	char *s;

	if ((token = ps->next_token) >= 0) {
		*value_p = ps->token_value;
		ps->next_token = -1;
		return token;
	}

	gemfile_parser_skip_whitespace(ps);

	memset(ps->token_value, 0, sizeof(ps->token_value));
	if (__gemfile_parser_at_eol(ps)) {
		ps->next = NULL;
		if (!ps->ignore_eol) {
			token = GEMFILE_T_EOL;
			goto done;
		}
		/* gemfile_parser_debug(ps, "Ignoring EOL\n"); */
	}

	while (ps->next == NULL) {
		unsigned int indent;

		ps->linebuf[0] = '\0';

		if (fgets(ps->linebuf, sizeof(ps->linebuf), ps->file) == NULL)
			return GEMFILE_T_EOF;

		ps->linebuf[strcspn(ps->linebuf, "\r\n")] = '\0';

		ps->next = ps->linebuf;
		ps->lineno += 1;

		indent = gemfile_parser_skip_whitespace(ps);

		/* Do something useful with indent? */
		(void) indent;

		if (__gemfile_parser_at_eol(ps)) {
			/* This line is empty (except maybe for a comment).
			 * Don't bother with reporting it though, as we've
			 * already reported the previous EOL */
			ps->next = NULL;
		}
	}

	token = GEMFILE_T_ERROR;

	s = ps->next;
	if (isalpha(*s)) {
		unsigned int i = 0;

		while (isalnum(*s) || *s == '_' || *s == '.')
			ps->token_value[i++] = *s++;

		token = GEMFILE_T_IDENTIFIER;
		ps->next = s;
	} else
	if (*s == '\'' || *s == '"') {
		char cc, quote_cc = *s++;
		unsigned int i = 0;

		while ((cc = *s++) != quote_cc) {
			if (cc == '\0') {
				gemfile_parser_error(ps, "Premature end of string\n");
				return GEMFILE_T_ERROR;
			}
			ps->token_value[i++] = cc;
		}

		token = GEMFILE_T_STRING;
		ps->next = s;
	} else
	if (*s == ':' && isalpha(s[1])) {
		unsigned int i = 0;

		s += 1;
		while (isalnum(*s) || *s == '_')
			ps->token_value[i++] = *s++;

		token = GEMFILE_T_SYMBOL;
		ps->next = s;
	} else {
		token = gemfile_parser_single_token(ps);
		if (token < 0) {
			gemfile_parser_error(ps, "Unable to parse next token\n");
			return GEMFILE_T_ERROR;
		}
	}

done:
	gemfile_parser_debug(ps, "%-12s %2u \"%s\"\n", gemfile_parser_token_name(token), token, ps->token_value);
	return token;
}

/* Get the next literal character from the parser. This is needed in order to
 * handle all the % nonsense in ruby.
 */
static char
gemfile_parser_next_character(gemfile_parser_state *ps)
{
	if (__gemfile_parser_at_eol(ps)) {
		gemfile_parser_err_unexpected_eol(ps);
		return '\0';
	}
	return *(ps->next++);
}

static inline void
__gemfile_parser_consume(gemfile_parser_state *ps)
{
	int i = strlen(ps->token_value); /* ugly */

	ps->token_value[i] = *(ps->next)++;
}

int
gemfile_parser_single_token(gemfile_parser_state *ps)
{
	static int single_tokens[256] = {
		[',']	= GEMFILE_T_COMMA,
		['[']	= GEMFILE_T_LBLOCKY,
		[']']	= GEMFILE_T_RBLOCKY,
		['(']	= GEMFILE_T_LBRACKET,
		[')']	= GEMFILE_T_RBRACKET,
		[':']	= GEMFILE_T_COLON,
		['?']	= GEMFILE_T_OPERATOR,
		['!']	= GEMFILE_T_OPERATOR,
		['=']	= GEMFILE_T_OPERATOR,
		['<']	= GEMFILE_T_OPERATOR,
		['>']	= GEMFILE_T_OPERATOR,
		['-']	= GEMFILE_T_OPERATOR,
		['+']	= GEMFILE_T_OPERATOR,
		['%']	= GEMFILE_T_PERCENT,
	};
	int token;

	token = single_tokens[(unsigned char) *(ps->next)];
	if (token <= 0)
		return -1;

	__gemfile_parser_consume(ps);

	switch (ps->token_value[0]) {
	case '=':
		if (ps->next[0] == '>')
			__gemfile_parser_consume(ps);
		break;
	case '>':
	case '<':
		if (ps->next[0] == '=')
			__gemfile_parser_consume(ps);
		break;
	}

	return token;
}

unsigned int
gemfile_parser_skip_whitespace(gemfile_parser_state *ps)
{
	unsigned int count = 0;
	char *s;

	if (ps->next == NULL)
		return 0;

	for (s = ps->next; *s && isspace(*s); ++s, ++count)
		;

	if (*s == '#')
		*s = '\0';

	ps->next = s;
	return count;
}

const char *
gemfile_parser_token_name(int token)
{
	if (token < 0)
		return "ERROR";

	assert(0 <= token && token <= __GEMFILE_T_MAX);
	return __gemfile_parser_token_names[token];
}

static void
string_array_destroy(string_array_t *array)
{
	unsigned int i;

	for (i = 0; i < array->count; ++i)
		drop_string(&array->value[i]);
	memset(array, 0, sizeof(*array));
}

static void
string_array_append(string_array_t *array, const char *value)
{
	assert(array->count < STRING_ARRAY_MAX);
	array->value[array->count++] = strdup(value);
}

static bool
string_array_contains(const string_array_t *array, const char *value)
{
	unsigned int i;

	// printf("%s([%s], %s)\n", __func__, string_array_print(array), value);
	if (!value)
		return false;
	for (i = 0; i < array->count; ++i) {
		const char *s = array->value[i];

		if (s && !strcmp(s, value))
			return true;
	}
	return false;
}

static const char *
__string_array_print(const string_array_t *array, char *buffer, size_t buffer_size)
{
	unsigned int i, pos, left;

	assert(buffer_size > 64);

	/* Reserve room for "...\0" */
	left = buffer_size - 4;

	for (i = pos = 0; i < array->count; ++i) {
		const char *word = array->value[i];
		unsigned int wlen = strlen(word);

		if (wlen + 2 > left) {
			strcpy(buffer + pos, "...");
			pos += 3;
			break;
		}

		if (i) {
			strcpy(buffer + pos, ", ");
			pos += 2;
		}

		strcpy(buffer + pos, word);
		pos += wlen;
	}

	return buffer;
}

const char *
string_array_print(const string_array_t *array)
{
	static char buffer[256];

	memset(buffer, 0, sizeof(buffer));
	return __string_array_print(array, buffer, sizeof(buffer));
}

static bundler_gem_t *
bundler_gem_array_extend(bundler_gem_array_t *array)
{
	assert(array->count < BUNDLER_GEM_ARRAY_MAX);

	if (array->count >= BUNDLER_GEM_ARRAY_MAX)
		return NULL;
	return &array->value[array->count++];
}

static void
bundler_gem_array_destroy(bundler_gem_array_t *array)
{
	unsigned int i;

	for (i = 0; i < array->count; ++i)
		bundler_gem_destroy(&array->value[i]);
	memset(array, 0, sizeof(*array));
}

static void
bundler_ivar_destroy(bundler_ivar_t *ivar)
{
	drop_string(&ivar->name);
	if (ivar->value) {
		bundler_value_release(ivar->value);
		ivar->value = NULL;
	}
}

static void
bundler_ivar_array_destroy(bundler_ivar_array_t *array)
{
	unsigned int i;

	for (i = 0; i < array->count; ++i)
		bundler_ivar_destroy(&array->value[i]);
	memset(array, 0, sizeof(*array));
}

static bundler_ivar_t *
bundler_ivar_array_extend(bundler_ivar_array_t *array)
{
	assert(array->count < BUNDLER_IVAR_ARRAY_MAX);

	if (array->count >= BUNDLER_IVAR_ARRAY_MAX)
		return NULL;
	return &array->value[array->count++];
}

static void
bundler_object_instance_destroy(bundler_object_instance_t *obj)
{
	bundler_ivar_array_destroy(&obj->ivars);
}

void
bundler_gem_destroy(bundler_gem_t *gem)
{
	drop_string(&gem->name);
	string_array_destroy(&gem->dependency);
	bundler_object_instance_destroy(&gem->base);
}

static void
bundler_gem_add_dependency(bundler_gem_t *gem, const char *s)
{
	if (gem->name == NULL)
		assign_string(&gem->name, s);
	else
		string_array_append(&gem->dependency, s);
}

static bundler_ivar_t *
bundler_gem_add_ivar(bundler_gem_t *gem, const char *name)
{
	bundler_ivar_t *ivar;

	ivar = bundler_ivar_array_extend(&gem->base.ivars);
	ivar->name = strdup(name);
	return ivar;
}

static bundler_ivar_t *
bundler_gem_get_ivar(bundler_gem_t *gem, const char *name)
{
	bundler_ivar_t *ivar;
	unsigned int i;

	for (i = 0; i < gem->base.ivars.count; ++i) {
		ivar = &gem->base.ivars.value[i];
		if (!strcmp(ivar->name, name))
			return ivar;
	}

	return NULL;
}

static bool
bundler_value_to_string_array(const bundler_value_t *v, string_array_t *array)
{
	const bundler_value_array_t *varr;
	unsigned int i;

	switch (v->type) {
	case VALUE_T_STRING:
		string_array_append(array, v->string);
		break;

	case VALUE_T_SYMBOL:
		string_array_append(array, v->symbol);
		break;

	case VALUE_T_ARRAY:
		varr = &v->array;
		for (i = 0; i < varr->count; ++i) {
			if (!bundler_value_to_string_array(varr->value[i], array))
				return false;
		}
		break;

	default:
		fprintf(stderr, "Unable to represent VALUE as string (%s)\n", bundler_value_print(v));
		return false;
	}

	return true;
}

static bool
bundler_gem_get_strings(bundler_gem_t *gem, const char *name, string_array_t *array)
{
	bundler_ivar_t *ivar;

	ivar = bundler_gem_get_ivar(gem, name);
	if (ivar == NULL)
		return false;

	return bundler_value_to_string_array(ivar->value, array);
}

static void
bundler_gem_apply_context(bundler_gem_t *gem, bundler_context_t *ctx)
{
	string_array_t strings = { .count = 0, };

	// If a gem's :platform or :platforms is set, but there's no match with our platform,
	// ignore the gem.
	//
	// If the context does not specify a platform, the comparison will return NO_FILTER
	// and hence bundler_gem_no_match will return false.
	bundler_gem_get_strings(gem, "platform", &strings);
	bundler_gem_get_strings(gem, "platforms", &strings);

	if (!bundler_context_match_platform(ctx, &strings)) {
		printf("%s: platform is set, but does not match ours\n", gem->name);
		gem->ignore = true;
	}

	string_array_destroy(&strings);

	// Look at the groups specified by this gem.
	bundler_gem_get_strings(gem, "group", &strings);
	bundler_gem_get_strings(gem, "groups", &strings);
	if (strings.count == 0)
		string_array_append(&strings, "default");

	if (!bundler_context_match_group(ctx, &strings)) {
		printf("%s: group is set, but does not match context groups\n", gem->name);
		gem->ignore = true;
	}

	string_array_destroy(&strings);
}

static bundler_gemfile_t *
bundler_gemfile_new(void)
{
	return calloc(1, sizeof(bundler_gemfile_t));
}

void
bundler_gemfile_set_source(bundler_gemfile_t *gemf, const char *value)
{
	assign_string(&gemf->source, value);
}

void
bundler_gemfile_add_gemspec(bundler_gemfile_t *gemf)
{
}

bundler_gem_t *
bundler_gemfile_add_gem(bundler_gemfile_t *gemf)
{
	return bundler_gem_array_extend(&gemf->gems);
}

static bool
gemfile_parser_err_unexpected(gemfile_parser_state *ps, int token)
{
	switch (token) {
	case GEMFILE_T_ERROR:
		gemfile_parser_error(ps, "Parse error\n");
		break;
	case GEMFILE_T_EOF:
		gemfile_parser_error(ps, "Unexpected end of file\n");
		break;
	case GEMFILE_T_EOL:
		gemfile_parser_error(ps, "Unexpected end of line\n");
		break;
	default:
		gemfile_parser_error(ps, "Unexpected token %s \"%s\"\n",
				gemfile_parser_token_name(token),
				ps->token_value);
		break;
	}

	return false;
}

static bool
gemfile_parser_err_unexpected_eol(gemfile_parser_state *ps)
{
	gemfile_parser_error(ps, "Unexpected end of line\n");
	return false;
}

static bool
__bundler_gemfile_eval_expect(gemfile_parser_state *ps, int expect_token)
{
	int token;

	token = gemfile_parser_next_token(ps, NULL);
	if (token != expect_token)
		return gemfile_parser_err_unexpected(ps, token);

	return true;
}

static inline bool
__bundler_gemfile_token_is_eol(int token)
{
	/* Wherever an EOL is valid, EOF is valid as well */
	return (token == GEMFILE_T_EOL || token == GEMFILE_T_EOF);
}

static bool
gemfile_parser_expect_eol(gemfile_parser_state *ps)
{
	int token;

	token = gemfile_parser_next_token(ps, NULL);
	if (!__bundler_gemfile_token_is_eol(token))
		return gemfile_parser_err_unexpected(ps, token);

	return true;
}

static inline const char *
gemfile_parser_expect_identifier(gemfile_parser_state *ps)
{
	if (!__bundler_gemfile_eval_expect(ps, GEMFILE_T_IDENTIFIER))
		return NULL;

	return ps->token_value;
}

static const char *
gemfile_parser_expect_string(gemfile_parser_state *ps)
{
	if (!__bundler_gemfile_eval_expect(ps, GEMFILE_T_STRING))
		return NULL;

	return ps->token_value;
}

static const char *
gemfile_parser_expect_symbol(gemfile_parser_state *ps)
{
	if (!__bundler_gemfile_eval_expect(ps, GEMFILE_T_SYMBOL))
		return NULL;

	return ps->token_value;
}

static bool
gemfile_parser_process_source(bundler_gemfile_t *gemf, gemfile_parser_state *ps)
{
	const char *string;

	if (!(string = gemfile_parser_expect_string(ps)))
		return false;

	if (ps->execute) {
		gemfile_parser_debug(ps, "Gemfile source is \"%s\"\n", string);
		bundler_gemfile_set_source(gemf, string);
	}

	return gemfile_parser_expect_eol(ps);
}

static bool
gemfile_parser_process_ruby(bundler_gemfile_t *gemf, gemfile_parser_state *ps)
{
	bundler_value_t *value;

	if (!(value = gemfile_parser_process_expression(ps)))
		return false;

	if (ps->execute) {
		gemfile_parser_debug(ps, "Gemfile specifies ruby version \"%s\"\n", bundler_value_print(value));
	}

	bundler_value_release(value);

	return gemfile_parser_expect_eol(ps);
}

static bool
gemfile_parser_process_gemspec(bundler_gemfile_t *gemf, gemfile_parser_state *ps)
{
	if (ps->execute) {
		gemfile_parser_debug(ps, "Gemfile specifies a gemspec\n");
		bundler_gemfile_add_gemspec(gemf);
	}

	return gemfile_parser_expect_eol(ps);
}

static bool
gemfile_parser_process_include(bundler_gemfile_t *gemf, gemfile_parser_state *ps)
{
	const char *string;
	char pathbuf[PATH_MAX];
	bool ok;

	if (!(string = gemfile_parser_expect_string(ps)))
		return false;

	gemfile_parser_debug(ps, "Including gemfile \"%s\"\n", string);

	if (string[0] != '/') {
		char *orig_filename;

		orig_filename = strdup(ps->filename);
		snprintf(pathbuf, sizeof(pathbuf), "%s/%s", dirname(orig_filename), string);
		free(orig_filename);
		string = pathbuf;
	}

	ps->nesting += 2;
	ok = __bundler_gemfile_eval(gemf, string, ps->bundler_ctx, ps->nesting + 2);
	ps->nesting -= 2;

	if (!ok)
		return ok;

	return gemfile_parser_expect_eol(ps);
}

static bool
gemfile_parser_process_group(bundler_gemfile_t *gemf, gemfile_parser_state *ps)
{
	string_array_t group_names = { .count = 0 };
	bool ok = false;
	int token;

	do {
		const char *symbol;

		symbol = gemfile_parser_expect_symbol(ps);
		if (symbol == NULL)
			return false;

		string_array_append(&group_names, symbol);

		token = gemfile_parser_next_token(ps, NULL);
	} while (token == GEMFILE_T_COMMA);

	if (__bundler_gemfile_token_is_eol(token)) {
		/* all is well */
		ok = true;
	} else
	if (token == GEMFILE_T_IDENTIFIER && !strcmp(ps->token_value, "do")) {
		bool execute = ps->execute;

		if (!gemfile_parser_expect_eol(ps))
			return false;

		if (!execute) {
			gemfile_parser_debug(ps, "== Skipping group check (execute=false)\n");
		} else
		if (!bundler_context_match_group(ps->bundler_ctx, &group_names)) {
			gemfile_parser_debug(ps, "== Groups names [%s] do not match context groups\n",
					string_array_print(&group_names));
			ps->execute = false;
		}

		ps->nesting += 2;
		ok = gemfile_parser_process_do_block(gemf, ps);
		ps->nesting -= 2;

		ps->execute = execute;
	} else {
                ok = gemfile_parser_err_unexpected(ps, token);
	}

	return ok;
}

static bool
gemfile_parser_process_platform(bundler_gemfile_t *gemf, gemfile_parser_state *ps)
{
	string_array_t platform_names = { .count = 0 };
	bool ok = false;
	int token;

	do {
		const char *symbol;

		symbol = gemfile_parser_expect_symbol(ps);
		if (symbol == NULL)
			return false;

		string_array_append(&platform_names, symbol);

		token = gemfile_parser_next_token(ps, NULL);
	} while (token == GEMFILE_T_COMMA);

	if (__bundler_gemfile_token_is_eol(token)) {
		/* all is well */
		ok = true;
	} else
	if (token == GEMFILE_T_IDENTIFIER && !strcmp(ps->token_value, "do")) {
		bool execute = ps->execute;

		if (!gemfile_parser_expect_eol(ps))
			return false;

		if (!execute) {
			gemfile_parser_debug(ps, "== Skipping platform check (execute=false)\n");
		} else
		if (!bundler_context_match_platform(ps->bundler_ctx, &platform_names)) {
			gemfile_parser_debug(ps, "== Platform names [%s] do not match context groups\n",
					string_array_print(&platform_names));
			ps->execute = false;
		}

		ps->nesting += 2;
		ok = gemfile_parser_process_do_block(gemf, ps);
		ps->nesting -= 2;

		ps->execute = execute;
	} else {
                ok = gemfile_parser_err_unexpected(ps, token);
	}

	return ok;
}

static bool
bundler_value_array_append(bundler_value_array_t *array, bundler_value_t *v)
{
	assert(array->count < VALUE_ARRAY_MAX);
	array->value[array->count++] = v;
	return true;
}

static bundler_value_t *
__bundler_value_new(int type)
{
	bundler_value_t *v;

	v = calloc(1, sizeof(*v));
	v->type = type;
	return v;
}

static bundler_value_t *
bundler_value_new_string(const char *s)
{
	bundler_value_t *v;

	v = __bundler_value_new(VALUE_T_STRING);
	v->string = s? strdup(s) : NULL;
	return v;
}

static bundler_value_t *
bundler_value_new_symbol(const char *s)
{
	bundler_value_t *v;

	v = __bundler_value_new(VALUE_T_SYMBOL);
	v->symbol = s? strdup(s) : NULL;
	return v;
}

static bundler_value_t *
bundler_value_new_array(void)
{
	return __bundler_value_new(VALUE_T_ARRAY);
}

static void
bundler_value_array_destroy(bundler_value_array_t *array)
{
	unsigned int i;

	for (i = 0; i < array->count; ++i)
		bundler_value_release(array->value[i]);
	memset(array, 0, sizeof(*array));
}

void
bundler_value_release(bundler_value_t *v)
{
	switch (v->type) {
	case VALUE_T_BOOL:
		return;

	case VALUE_T_ARRAY:
		bundler_value_array_destroy(&v->array);
		break;
	
	default:
		break;
	}

	free(v);
}

static bool
bundler_value_append(bundler_value_t *obj, bundler_value_t *item)
{
	if (obj->type != VALUE_T_ARRAY) {
		fprintf(stderr, "Don't know how to append to value type %d\n", obj->type);
		return false;
	}

	/* printf("array %p append %s\n", obj, bundler_value_print(item)); */
	return bundler_value_array_append(&obj->array, item);
}

static const char *
__bundler_value_print(const bundler_value_t *v, char *buffer, size_t size)
{
	switch (v->type) {
	case VALUE_T_BOOL:
		return (v->boolean? "true" : "false");
	case VALUE_T_STRING:
		snprintf(buffer, size, "\"%s\"", v->string);
		return buffer;
	case VALUE_T_SYMBOL:
		snprintf(buffer, size, ":%s", v->symbol);
		return buffer;
	case VALUE_T_ARRAY:
		{
			string_array_t temp = { .count = 0 };
			char localbuf[256];
			unsigned int i;

			for (i = 0; i < v->array.count; ++i)
				string_array_append(&temp, __bundler_value_print(v->array.value[i], buffer, size));

			snprintf(buffer, size, "[%s]", __string_array_print(&temp, localbuf, sizeof(localbuf)));
			string_array_destroy(&temp);
		}
		return buffer;
	default:
		break;
	}
	return "<OTHER>";
}

const char *
bundler_value_print(const bundler_value_t *v)
{
	static char buffer[1024];

	return __bundler_value_print(v, buffer, sizeof(buffer));
}

/*
 * Parse one of these funky ruby %w literals
 */
static bundler_value_t *
gemfile_parser_process_literal_percent_w(gemfile_parser_state *ps)
{
	bundler_value_t *v;
	char cc, left, right;
	char word[256];
	unsigned int word_len;

	left = gemfile_parser_next_character(ps);
	if (left == '\0')
		return NULL;

	switch (left) {
	case '[':	right = ']'; break;
	case '(':	right = ')'; break;
	case '{':	right = '}'; break;
	default:	right = left;
	}

	gemfile_parser_debug(ps, "Parsing literal %%w%c...%c\n", left, right);
	v = bundler_value_new_array();

	memset(word, 0, sizeof(word));
	word_len = 0;

	while ((cc = gemfile_parser_next_character(ps)) != '\0') {
		if (cc == right || isspace(cc)) {
			if (word_len) {
				gemfile_parser_debug(ps, "%-12s %2u \"%s\"\n", gemfile_parser_token_name(GEMFILE_T_STRING), GEMFILE_T_STRING, word);
				bundler_value_append(v, bundler_value_new_string(word));
				memset(word, 0, sizeof(word));
				word_len = 0;
			}
		}

		if (cc == right)
			return v;

		if (!isspace(cc)) {
			if (word_len + 2 >= sizeof(word)) {
				gemfile_parser_error(ps, "Word in %w literal too long\n");
				goto failed;
			}
			word[word_len++] = cc;
		}
	}

	gemfile_parser_err_unexpected_eol(ps);

failed:
	bundler_value_release(v);
	return false;
}

/*
 * This is a very simple kind of expression, without any infix
 * operators at all.
 */
static bundler_value_t *
gemfile_parser_process_expression(gemfile_parser_state *ps)
{
	static bundler_value_t value_false = { .type = VALUE_T_BOOL, .boolean = false };
	static bundler_value_t value_true = { .type = VALUE_T_BOOL, .boolean = true };
	int token;

	token = gemfile_parser_next_token(ps, NULL);
	if (token == GEMFILE_T_IDENTIFIER) {
		if (!strcmp(ps->token_value, "false"))
			return &value_false;
		if (!strcmp(ps->token_value, "true"))
			return &value_true;
		if (!strcmp(ps->token_value, "RUBY_VERSION")) {
			if (ps->bundler_ctx == NULL) {
				/* complain? */
				return NULL;
			}
			return bundler_value_new_string(ps->bundler_ctx->ruby_version);
		}
	} else if (token == GEMFILE_T_STRING) {
		return bundler_value_new_string(ps->token_value);
	} else if (token == GEMFILE_T_SYMBOL) {
		return bundler_value_new_symbol(ps->token_value);
	} else if (token == GEMFILE_T_LBLOCKY) {
		bundler_value_t *v = bundler_value_new_array();

		ps->ignore_eol ++;
		do {
			bundler_value_t *item;

			if (!(item = gemfile_parser_process_expression(ps)))
				return NULL;
			bundler_value_append(v, item);

			token = gemfile_parser_next_token(ps, NULL);
		} while (token == GEMFILE_T_COMMA);
		ps->ignore_eol --;

		if (token == GEMFILE_T_RBLOCKY)
			return v;
	} else if (token == GEMFILE_T_PERCENT) {
		char cc;

		cc = gemfile_parser_next_character(ps);
		if (cc == '\0')
			return NULL;

		if (cc == 'w')
			return gemfile_parser_process_literal_percent_w(ps);

		gemfile_parser_error(ps, "Unsupported %%%c literal\n", cc);
		return NULL;
	}

	gemfile_parser_err_unexpected(ps, token);
	return NULL;
}

static bool
gemfile_parser_process_gem(bundler_gemfile_t *gemf, gemfile_parser_state *ps)
{
	bundler_gem_t *gem;
	int token;

	gem = bundler_gemfile_add_gem(gemf);

	/* ugly */
	gem->ignore = !ps->execute;

	do {
		token = gemfile_parser_next_token(ps, NULL);

		if (token == GEMFILE_T_STRING) {
			bundler_gem_add_dependency(gem, ps->token_value);
		} else if (token == GEMFILE_T_SYMBOL) {
			bundler_ivar_t *ivar;

			ivar = bundler_gem_add_ivar(gem, ps->token_value);
			if (!ivar) {
				fprintf(stderr, "Cannot create instance var :%s\n", ps->token_value);
				return false;
			}

			if (!__bundler_gemfile_eval_expect(ps, GEMFILE_T_OPERATOR))
				return false;
			if (strcmp(ps->token_value, "=>")) {
				fprintf(stderr, "Expected operator => but got \"%s\"\n", ps->token_value);
				return false;
			}

			/* get the instance var value */
			ivar->value = gemfile_parser_process_expression(ps);
			if (ivar->value == NULL)
				return false;

			gemfile_parser_debug(ps, "== Set instance var gem.%s=%s\n", ivar->name, bundler_value_print(ivar->value));
		} else if (token == GEMFILE_T_IDENTIFIER) {
			bundler_ivar_t *ivar;

			ivar = bundler_gem_add_ivar(gem, ps->token_value);
			if (!ivar) {
				fprintf(stderr, "Cannot create var %s\n", ps->token_value);
				return false;
			}

			if (!__bundler_gemfile_eval_expect(ps, GEMFILE_T_COLON))
				return false;

			/* get the variable value */
			ivar->value = gemfile_parser_process_expression(ps);
			if (ivar->value == NULL)
				return false;

			gemfile_parser_debug(ps, "== Set var gem.%s=%s\n", ivar->name, bundler_value_print(ivar->value));
		} else
			return gemfile_parser_err_unexpected(ps, token);

		token = gemfile_parser_next_token(ps, NULL);
	} while (token == GEMFILE_T_COMMA);

	if (!__bundler_gemfile_token_is_eol(token))
		return gemfile_parser_err_unexpected(ps, token);

	if (ps->bundler_ctx)
		bundler_gem_apply_context(gem, ps->bundler_ctx);

	if (gem->ignore)
		gemfile_parser_debug(ps, "== Gem %s is being ignored\n", gem->name);

	return true;
}

struct block_context {
	bundler_gemfile_t *	gemfile;
	__gemfile_parser_statement_handler_t *handler;
	const char **		valid_end_stmts;
};

static const char *
__find_identifier_in_list(const char ** list, const char *ident)
{
	const char *s;

	if (!list)
		return NULL;

	while ((s = *list++) != NULL && strcmp(s, ident))
		;
	return s;
}

static const char *
gemfile_parser_process_code_block(struct block_context *ctx, gemfile_parser_state *ps)
{
	const char *end_stmt = NULL;

	while (true) {
		const char *identifier;
		int token;

		token = gemfile_parser_next_token(ps, NULL);
		if (token == GEMFILE_T_EOF && ctx->valid_end_stmts == NULL)
			return "EOF";

		if (token != GEMFILE_T_IDENTIFIER) {
			gemfile_parser_err_unexpected(ps, token);
			return NULL;
		}

		identifier = ps->token_value;

		if ((end_stmt = __find_identifier_in_list(ctx->valid_end_stmts, identifier)) != NULL)
			break;

		if (!strcmp(identifier, "if")) {
			fprintf(stderr, "if command not implemented\n");
			break;
		} else
		if (!ctx->handler(ctx->gemfile, ps, identifier)) {
			break;
		}
	}

	if (end_stmt != NULL && !gemfile_parser_expect_eol(ps))
		end_stmt = NULL;

	return end_stmt;
}

static bool
gemfile_parser_process_statement(bundler_gemfile_t *gemf, gemfile_parser_state *ps, const char *identifier)
{
	if (!strcmp(identifier, "source")) {
		return gemfile_parser_process_source(gemf, ps);
	} else if (!strcmp(identifier, "ruby")) {
		return gemfile_parser_process_ruby(gemf, ps);
	} else if (!strcmp(identifier, "gemspec")) {
		return gemfile_parser_process_gemspec(gemf, ps);
	} else if (!strcmp(identifier, "group")) {
		return gemfile_parser_process_group(gemf, ps);
	} else if (!strcmp(identifier, "platforms") || !strcmp(identifier, "platform")) {
		return gemfile_parser_process_platform(gemf, ps);
	} else if (!strcmp(identifier, "gem")) {
		return gemfile_parser_process_gem(gemf, ps);
	} else if (!strcmp(identifier, "eval_gemfile")) {
		return gemfile_parser_process_include(gemf, ps);
	}

	return gemfile_parser_err_unexpected(ps, GEMFILE_T_IDENTIFIER);
}

static bool
gemfile_parser_process_do_block(bundler_gemfile_t *gemf, gemfile_parser_state *ps)
{
	static const char *	end_statements[] = { "end", NULL };
	struct block_context	do_block_context = {
		.gemfile = gemf,
		.handler = gemfile_parser_process_statement,
		.valid_end_stmts = end_statements
	};

	return gemfile_parser_process_code_block(&do_block_context, ps);
}

static bool
gemfile_parser_process_toplevel(bundler_gemfile_t *gemf, gemfile_parser_state *ps)
{
	struct block_context	file_block_context = {
		.gemfile = gemf,
		.handler = gemfile_parser_process_statement,
		.valid_end_stmts = NULL /* indicates that the block ends with EOF */
	};

	ps->execute = true;
	return gemfile_parser_process_code_block(&file_block_context, ps);
}

void
bundler_gemfile_free(bundler_gemfile_t *gemf)
{
	drop_string(&gemf->source);

	bundler_gem_array_destroy(&gemf->gems);
	free(gemf);
}

bundler_context_t *
bundler_context_new(const char *ruby_version)
{
	bundler_context_t *ctx;

	ctx = calloc(1, sizeof(*ctx));
	bundler_context_set_ruby_version(ctx, ruby_version);
	string_array_append(&ctx->with_groups, "default");
	return ctx;
}

void
bundler_context_set_ruby_version(bundler_context_t *ctx, const char *ruby_version)
{
	char short_version[128];
	char platform[128];
	unsigned int i = 0;
	const char *s;

	assert(strlen(ruby_version) < 64);

	assign_string(&ctx->ruby_version, ruby_version);
	string_array_destroy(&ctx->platforms);

	string_array_append(&ctx->platforms, "ruby");
	string_array_append(&ctx->platforms, "mri");

	if (ruby_version == NULL)
		return;

	for (s = ruby_version; *s && *s != '.'; ++s)
		short_version[i++] = *s;

	if (*s == '.') {
		++s;
		for (; *s && *s != '.'; ++s)
			short_version[i++] = *s;
	}
	short_version[i] = '\0';

	snprintf(platform, sizeof(platform), "ruby_%s", short_version);
	string_array_append(&ctx->platforms, platform);

	snprintf(platform, sizeof(platform), "mri_%s", short_version);
	string_array_append(&ctx->platforms, platform);
}

void
bundler_context_with_group(bundler_context_t *ctx, const char *name)
{
	string_array_append(&ctx->with_groups, name);
}

void
bundler_context_without_group(bundler_context_t *ctx, const char *name)
{
	string_array_append(&ctx->without_groups, name);
}

bool
bundler_context_match_platform(bundler_context_t *ctx, const string_array_t *names)
{
	unsigned int i;

	/* Gem does not specify any platforms: no restrictions */
	if (names->count == 0)
		return true;

	for (i = 0; i < names->count; ++i) {
		if (string_array_contains(&ctx->platforms, names->value[i]))
			return true;
	}

	return false;
}

bool
bundler_context_match_group(bundler_context_t *ctx, const string_array_t *names)
{
	unsigned int i;
	bool with = false, without = false;

	/* Gem does not specify any groups: place it in :default */
	if (names->count == 0)
		return string_array_contains(&ctx->with_groups, "default");

	for (i = 0; i < names->count; ++i) {
		const char *group = names->value[i];

		if (string_array_contains(&ctx->with_groups, group))
			with = true;

		if (string_array_contains(&ctx->without_groups, group))
			without = true;
	}

	if (without)
		return false;

	return with;
}

void
bundler_context_free(bundler_context_t *ctx)
{
	drop_string(&ctx->ruby_version);
	string_array_destroy(&ctx->platforms);
	free(ctx);
}

bool
__bundler_gemfile_eval(bundler_gemfile_t *gemf, const char *path, bundler_context_t *ctx, unsigned int nesting)
{
	gemfile_parser_state parser;
	FILE *fp;
	bool rv;

	if ((fp = fopen(path, "r")) == NULL) {
		// return bundler_parse_error(error_msg_p, "Unable to open %s: %m", path);
		fprintf(stderr, "Unable to open %s: %m\n", path);
		return false;
	}

	gemfile_parser_init(&parser, path, fp, ctx);
	parser.nesting = nesting;
	parser.debug = true;

	rv = gemfile_parser_process_toplevel(gemf, &parser);

	gemfile_parser_debug(&parser, "Successfully parsed file\n");
	gemfile_parser_destroy(&parser);

	return rv;
}

bundler_gemfile_t *
bundler_gemfile_parse(const char *path, bundler_context_t *ctx, char **error_msg_p)
{
	bundler_gemfile_t *gemf;

	gemf = bundler_gemfile_new();

	if (!__bundler_gemfile_eval(gemf, path, ctx, 0)) {
		/* set error_msg_p to something useful */
		bundler_gemfile_free(gemf);
		return NULL;
	}

	return gemf;
}

