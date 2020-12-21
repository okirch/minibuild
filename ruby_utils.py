#!/usr/bin/python3

import marshal48
import io
import copy

class Ruby:
	class ParsedVersion(object):
		def __init__(self, s):
			self._version = []
			self.is_prerelease = False

			if type(s) == list or type(s) == tuple:
				self._version = s
				return

			if type(s) != str:
				raise ValueError("Cannot build ParsedVersion from %s object (%s)" % (
						type(s), s))

			word = None
			isnumber = False
			for cc in s:
				if cc == '.':
					if word is not None:
						self._version.append(word)
					self._version.append('.')
					word = None
					continue

				if word is not None:
					if isnumber == cc.isdigit():
						word += cc;
						continue

					self._version.append(word)

				isnumber = cc.isdigit()
				word = cc

			if word is not None:
				self._version.append(word)

			for i in range(len(self._version)):
				try:
					self._version[i] = int(self._version[i])
				except:
					pass

			assert(self._version[-1] != '.')

		def next_bigger(self):
			# This is here to support ~> comparison.
			# ~> 3.0.3 means ">= 3.0.3, <3.1"
			# ~> 2 means '>= 2.0, < 3.0'
			next_version = self._next_bigger()
			# print("next_bigger(%s) => %s" % (self._version, next_version))
			return Ruby.ParsedVersion(next_version)

		def _next_bigger(self):
			version = copy.copy(self._version)

			if len(version) == 1:
				return [version[0] + 1]

			while version[-1] != '.':
				version.pop()

			while version:
				last = version.pop()
				if last == '.':
					break

			last = version.pop()
			if type(last) != int:
				last = version.pop()

			version.append(last + 1)
			return version

		def __repr__(self):
			return "".join([str(x) for x in self._version])

		def __lt__(self, other):
			return self.compare(other, lambda s, o: s < o)

		def __gt__(self, other):
			return self.compare(other, lambda s, o: s > o)

		def __le__(self, other):
			return self.compare(other, lambda s, o: s <= o)

		def __ge__(self, other):
			return self.compare(other, lambda s, o: s >= o)

		def __eq__(self, other):
			return self.compare(other, lambda s, o: s == o)

		def __ne__(self, other):
			return self.compare(other, lambda s, o: s != o)

		def compare(self, other, f):
			for a, b in zip(self._version, other._version):
				if a == b:
					continue
				return f(a, b)

			return f(len(self._version), len(other._version))

	class GemVersion(object):
		# Needed for marshaling
		ruby_classname = 'Gem::Version'

		def __init__(self, yaml_data = None):
			self.versions = []

			if yaml_data:
				self.versions.append(yaml_data['version'])

		@property
		def version(self):
			return self.versions[0]

		def marshal_load(self, array):
			# print("GemVersion.marshal_load(%s)" % array)
			assert(len(array) == 1)

			for o in array:
				self.versions.append(str(o))

		def __str__(self):
			if len(self.versions) == 1:
				return self.versions[0]
			return "[%s]" % ", ".join(self.versions)

		def __repr__(self):
			if len(self.versions) == 1:
				return self.versions[0]
			return "[%s]" % ", ".join(self.versions)

		def __eq__(self, other):
			assert(isinstance(other, self.__class__))
			return self.versions == other.versions

	class Clause:
		def __init__(self, op, version):
			self.op = op
			self.version = Ruby.ParsedVersion(str(version))

		def __repr__(self):
			return "%s %s" % (self.op, self.version)

		def __contains__(self, item):
			return self.contains(item)

		def contains(self, item):
			op = self.op
			if op == '==' or op == '=':
				return item == self.version
			if op == '!=':
				return item != self.version
			if op == '>=':
				return item >= self.version
			if op == '<=':
				return item <= self.version
			if op == '>':
				return item > self.version
			if op == '<':
				return item < self.version
			if op == '~>':
				return item >= self.version and item < self.version.next_bigger()

			raise ValueError("Unknown version comparison operator \"%s\"" % self.op)

		def __eq__(self, other):
			assert(isinstance(other, self.__class__))
			return self.op == other.op and self.version == other.version

	class GemRequirement(object):
		# Needed for marshaling
		ruby_classname = 'Gem::Requirement'

		def __init__(self, yaml_data = None):
			self.req = []

			if yaml_data is not None:
				for op, version in yaml_data['requirements']:
					self.req.append(Ruby.Clause(op, version))

		def add_clause(self, c):
			self.req.append(c)

		def marshal_load(self, data):
			# Calls look like
			# GemRequirement.marshal_load([[['>=', 3.0.0]]])
			# print("GemRequirement.marshal_load(%s)" % data)
			if type(data) == list and len(data) == 1:
				data = data[0]

			for r in data:
				# print("  %s" % r)
				self.req.append(Ruby.Clause(*r))

		def __repr__(self):
			return "%s" % (", ".join(str(r) for r in self.req))

		@staticmethod
		def parse(string):
			# print("GemRequirement.parse(%s)" % string)
			result = Ruby.GemRequirement()

			for req in string.split(','):
				req = req.replace(' ', '')
				if not req:
					continue

				for i in range(len(req)):
					if req[i] not in "<>=!~":
						break

				# print("  %s|%s" % (req[:i], req[i:]))
				result.add_clause(Ruby.Clause(req[:i], req[i:]))

			return result

		def __contains__(self, item):
			return self.contains(item)

		def contains(self, item):
			if not isinstance(item, Ruby.ParsedVersion):
				item = Ruby.ParsedVersion(item)

			return all(s.contains(item) for s in self.req)

		def __iter__(self):
			return iter(self.req)

		def __eq__(self, other):
			assert(isinstance(other, self.__class__))
			return self.req == other.req

	class GemDependency(object):
		# Needed for marshaling
		ruby_classname = 'Gem::Dependency'

		def __init__(self, yaml_data = None):
			self.name = None
			self.requirement = Ruby.GemRequirement()
			self.type = 'any'
			self.prerelease = False

			if yaml_data:
				self.name = yaml_data['name']
				self.requirement = yaml_data['requirement']
				self.type = yaml_data['type']
				if self.type.startswith(':'):
					self.type = self.type.lstrip(':')
				self.prerelease = yaml_data['prerelease']
				# ignoring version_requirements

		def __repr__(self):
			return "GemDependency(%s %s%s%s)" % (
					self.name,
					str(self.requirement),
					self.type != "runtime" and "; " + self.type or "",
					self.prerelease and "; prerelease" or ""
					)

		def __contains__(self, arg):
			# print("%s.__contains__(%s))" % (self, arg))

			name, version = arg
			if self.name != name:
				return False

			return version in self.requirement

		def format(self, include_attrs = True):
			result = self.name + " " + self.format_versions()
			if include_attrs:
				if self.prerelease:
					result += "; prerelease"
				if self.type != 'any':
					result += "; " + self.type
			return result

		def format_versions(self):
			result = ", ".join([str(x) for x in self.requirement])
			if result == ">= 0":
				result = ""
			return result

		def __eq__(self, other):
			assert(isinstance(other, self.__class__))

			if self.name != other.name or \
			   self.prerelease != other.prerelease or \
			   self.type != other.type:
				return False

			if self.requirement != other.requirement:
				return False

			return True

		@staticmethod
		def parse(string):
			def findsep(s):
				for n in range(len(s)):
					if s[n] in " <>=!~":
						return n
				return -1

			# print("GemDependency.parse(%s)" % string)
			dep = Ruby.GemDependency()

			n = findsep(string)
			if n < 0:
				dep.name = string
				return dep

			dep.name = string[:n]
			string = string[n:]

			w = string.split(';')
			dep.requirement = Ruby.GemRequirement.parse(w.pop(0))

			for mod in w:
				mod = mod.replace(' ', '')
				if mod == 'prerelease':
					self.prerelease = True
				else:
					dep.type = mod

			return dep

	class GemPlatform(object):
		# Gem::Platform(); {@cpu=None, @os=java, @version=None}
		def __init__(self, yaml_data = None):
			self.cpu = None
			self.os = None
			self.version = None

			if yaml_data is not None:
				for key, value in yaml_data.items():
					setattr(self, key, value)
			self._yaml = yaml_data

		def __repr__(self):
			if not self.cpu and not self.os and not self.version:
				return "ruby"
			l = []
			if self.cpu:
				l.append(self.cpu)
			if self.os:
				l.append(self.os)
			if self.version:
				l.append(self.version)
			return "-".join(l)

	@staticmethod
	def parse_dependency(string):
		return Ruby.GemDependency.parse(string)

	class GemSpecification(object):
		signature_v4 = (
				'rubygems_version',
				'specification_version',# int, usually 4
				'name',			# string
				'version',		# Gem::Version
				'date',			# Time() with instance vars
				'summary',		# string
				'required_ruby_version', # Gem::Dependency
				'required_rubygems_version', # Gem::Dependency
				'platform',		# string, aka "original_platform"
				'dependencies',		# array of Gem::Dependencies
				'rubyforge_project',	# string, usually empty
				'email',		# string or array of strings
				'author',		# string or array of strings
				'description',		# string
				'homepage',		# string
				'has_rdoc',		# boolean
				'new_platform',		# dup of platform

				# Added in v3
				'licenses',		# array of strings

				# Added in v4
				'metadata',		# hash
		)

		# Needed for marshaling
		ruby_classname = 'Gem::Specification'

		def __init__(self, yaml_data = None):
			self.name = None
			self.version = None
			self.summary = None
			self.dependencies = None
			self.rubygems_version = None
			self.required_ruby_version = None
			self._required_rubygems_version = None
			self.metadata = None
			self._emails = []
			self._authors = []
			self.dependencies = []

			if yaml_data is not None:
				for key, value in yaml_data.items():
					setattr(self, key, value)
			self._yaml = yaml_data

		@property
		def email(self):
			if len(self._emails):
				return self._emails[0]
			return None

		@email.setter
		def email(self, value):
			if type(value) == list:
				self._emails = value
			else:
				self._emails = [value]

		@property
		def author(self):
			if len(self._authors):
				return self._authors[0]
			return None

		@author.setter
		def author(self, value):
			if type(value) == list:
				self._authors = value
			else:
				self._authors = [value]

		@property
		def required_rubygems_version(self):
			return self._required_rubygems_version

		@required_rubygems_version.setter
		def required_rubygems_version(self, value):
			if value is not None and not isinstance(value, Ruby.GemRequirement):
				raise ValueError("marshalled gemspec for %s-%s specifies invalid required_rubygems_version=\"%s\"" % (
					self.name, self.version, value
				))
				return
			self._required_rubygems_version = value

		def load(self, data):
			# print("GemSpecification.load(%s)" % data)
			data = unmarshal_byteseq(data)

			gemspec_version = data[1]
			if gemspec_version <= 4:
				sig = self.signature_v4
			else:
				if True:
					print("Unknown gemspec version %s" % gemspec_version)
					print("Data:")
					for i in range(len(data)):
						print(i, data[i])

				raise ValueError("Don't know how to deal with gemspec version %d data" % gemspec_version)

			if len(data) > len(sig):
				print("WARNING: GemSpecification.load: gemspec ver %s has %u elements (expected at most %u)" % (
					gemspec_version, len(data), len(sig)))

			for attr_name, value in zip(sig, data):
				# print("%s=%s" % (attr_name, value))
				setattr(self, attr_name, value)

		def __repr__(self):
			return "GemSpecification(%s-%s)" % (self.name, self.version)

		class ObjectDiffer:
			def __init__(self, name = "GemSpecification"):
				self._changed = dict()
				self.name = name

			class Change:
				def __init__(self, old, new):
					self.badness = 1000
					self.old = old
					self.new = new

				def display(self, key):
					print("  %s (badness %d): \"%s\" -> \"%s\"" % (key, self.badness, self.old, self.new))

				def diff_display(self, indent = ""):
					if self.old:
						print("%s- %s" % (indent, self.old))
					if self.new:
						print("%s+ %s" % (indent, self.new))

			class ListChange:
				def __init__(self, items):
					self.badness = 1000
					self.items = items

				def display(self, key):
					if not self.items:
						print("  %s: no changes" % key)
						return

					print("  %s changes (badness %d):" % (key, self.badness))
					for item in self.items:
						item.diff_display("    ")

			def add(self, key, our_value, her_value):
				# print("Change %s: \"%s\"/%s -> \"%s\"/%s" % (key, our_value, type(our_value), her_value, type(her_value)))
				change = self.__class__.Change(our_value, her_value)
				self._changed[key] = change
				return change

			def add_list_diff(self, key, our_value, her_value):
				our_value = set(our_value)
				her_value = set(her_value)
				not_common = our_value.symmetric_difference(her_value)

				changes = []
				# print("Change %s:" % key)
				for item in not_common:
					if item in our_value:
						# print("- %s" % item)
						changes.append(self.__class__.Change(item, None))
					else:
						# print("+ %s" % item)
						changes.append(self.__class__.Change(None, item))

				if not changes:
					# print("NO CHANGE")
					return None

				change = self.__class__.ListChange(changes)
				self._changed[key] = change
				return change

			def show(self):
				if not self._changed:
					print("%s - no changes" % self.name)
					return

				print("%s changes:" % self.name)
				for key in sorted(self._changed.keys()):
					d = self._changed[key]
					d.display(key)

			def __bool__(self):
				return not not self._changed

			def badness(self):
				if not self._changed:
					return 0
				return max([change.badness for change in self._changed.values()])

		def diff(self, other, badness_map = dict()):
			assert(isinstance(other, self.__class__))

			# For now, we will only compare a GemSpecification loaded from yaml
			assert(self._yaml and other._yaml)

			result = Ruby.GemSpecification.ObjectDiffer()
			if self._yaml and other._yaml:
				all_keys = set(self._yaml.keys()).union(set(other._yaml.keys()))
				for key in sorted(all_keys):
					our_value = self._yaml.get(key)
					her_value = other._yaml.get(key)
					if our_value == her_value:
						continue

					if type(our_value) == list and type(her_value) == list:
						change = result.add_list_diff(key, our_value, her_value)
					else:
						change = result.add(key, our_value, her_value)

					if change:
						change.badness = badness_map.get(key, 100)

			return result

	class Time:
		# Needed for marshaling
		ruby_classname = 'Time'

		def __init__(self):
			self.timedata = None

			self.tzmode = 0
			self.year = 0
			self.month = 0
			self.mday = 0

		def load(self, data):
			# print("Time.load(%s)" % data)
			assert(len(data) == 8)
			self.timedata = data

			# Lovely encoding of Time objects. To round things out, they
			# could have used a BCD format to represent integers...
			value = 0
			for i in range(4):
				value += data[i] << (8 * i)

			# The MSB is always 1
			assert(value & 0x80000000)

			self.tzmode = (0x0001 & (value >> 30))
			self.year   = (0xFFFF & (value >> 14)) + 1900
			self.month  = (0x000F & (value >> 10)) + 1
			self.mday   = (0x001F & (value >>  5))

			# assert(self.tzmode == 1)

			# The timestamps contained in gem metadata only provide a date,
			# never seconds or subsecond values. So we ignore the rest.

		def __repr__(self):
			return "%d-%02d-%02d 00:00:00.000000000 Z" % (self.year, self.month, self.mday)

	classes = {
		'Gem::Version'		: GemVersion,
		'Gem::Specification'	: GemSpecification,
		'Gem::Requirement'	: GemRequirement,
		'Gem::Dependency'	: GemDependency,
		'Gem::Platform'		: GemPlatform,
		'Time'			: Time,
	}

	def find_class(name):
		return Ruby.classes.get(name)

	@staticmethod
	def factory(name, *args):
		cls = Ruby.find_class(name)
		if not cls:
			raise NotImplementedError("Ruby.factory: unknown class %s" % name)

		return cls(*args)

	class YAML:
		initialized = False

		class PartiallyConstructedObject:
			def __init__(self, name, value):
				self.name = name
				self.value = value

			def __repr__(self):
				return "Interim::%s(%s)" % (self.name, self.value)

			def finalize(self):
				# print("Finalizing", self)
				value = self.finalize_one(self.value)

				return Ruby.factory(self.name, value)

			def finalize_one(self, value):
				t = type(value)
				if t == list:
					return [self.finalize_one(item) for item in value]
				if t == dict:
					return {k: self.finalize_one(v) for k, v in value.items()}
				if t == type(self):
					return value.finalize()
				return value


		# Constructing objects from the yaml stream is a bit more convoluted than
		# seems adequate. That's because the loader will /not/ convert the value
		# completely in loader.construct_mapping(). For example, the value of a
		# Gem::Requirement will be a mapping with
		#	'requirements' : []
		# The actual data that should be _in_ this list will only be converted
		# at a later point. Maybe because the constructor() code in yaml is not
		# able to deal with recursive calls or some such problem...
		@staticmethod
		def multi_constructor(loader, tag_suffix, node):
			mapping = loader.construct_mapping(node)

			if False:
				print("%s to be created with mapping:" % tag_suffix)
				for k, v in mapping.items():
					print("  %s=%s" % (k, v))

			return Ruby.YAML.PartiallyConstructedObject(tag_suffix, mapping)

		@staticmethod
		def initonce():
			import yaml

			if not Ruby.YAML.initialized:
				yaml.add_multi_constructor('!ruby/object:',
						Ruby.YAML.multi_constructor,
						Loader = yaml.Loader)
				Ruby.YAML.initialized = True

		@staticmethod
		def load(io):
			import yaml

			Ruby.YAML.initonce()

			ret = yaml.load(io, Loader = yaml.Loader)
			return ret.finalize()


	class GemfileLock:
		class Node:
			def __init__(self, name = None, value = None):
				self.name = name
				self.value = value or ""
				self.children = []

			def find(self, name):
				for node in self.children:
					if node.name == name:
						return node
				return None

			def dump(self, indent = ""):
				print("%s%s %s" % (indent, self.name, self.value))
				for node in self.children:
					node.dump(indent + "  ")

		def __init__(self, topNode):
			self.node = topNode

		def dump(self):
			return self.node.dump()

		@staticmethod
		def parse(fsResource):
			import re

			top = Ruby.GemfileLock.Node()

			current = top
			prev = None
			indent = ""
			stack = []
			with fsResource.open('r') as f:
				for l in f.readlines():
					while not l.startswith(indent):
						(current, indent) = stack.pop()

					l = l[len(indent):].rstrip()

					# If indentation level increases, we're starting
					# a nested group
					if l.startswith(' '):
						assert(prev)
						stack.append((current, indent))
						current = prev

						# clumsy
						while l.startswith(' '):
							indent += ' '
							l = l[1:]

					# parse identifier
					m = re.search('([^ :]*)[ :]*(.*)', l)
					if not m:
						raise ValueError(l)

					id = m.group(1)
					rest = m.group(2)
					node = Ruby.GemfileLock.Node(id, rest)
					current.children.append(node)
					prev = node

			return Ruby.GemfileLock(top)

		def lookup(self, name):
			node = self.node
			for n in name.split('.'):
				if node is None:
					break
				node = node.find(n)

			return node

		def requirements(self):
			result = []

			specs = self.lookup("GEM.specs")
			if specs:
				for child in specs.children:
					result += self._requirements(child)

			return result

		def _requirements(self, node):
			result = []

			# A Gemlock GEM entry can take several forms
			#  name!
			#	Used to refer to the gem being built
			#  name
			#	No version info
			#  name (>= 1.2.4)
			#	Requirement in parentheses
			#  name (1.2.4)
			#	Exact version number in parentheses
			if not node.name.endswith('!'):
				req_name = node.name
				req_version = node.value.strip("()")

				if not req_version:
					req_string = req_name
				elif not req_version[0].isdigit():
					req_string = "%s %s" % (req_name, req_version)
				else:
					req_string = "%s == %s" % (req_name, req_version)
				req = Ruby.GemDependency.parse(req_string)
				result.append(req)

			for child in node.children:
				result += self._requirements(child)

			return result

		def build_targets(self):
			result = []

			specs = self.lookup("PATH.specs")
			if specs:
				print("  Build target(s):")
				for node in specs.children:
					print("    %s %s" % (node.name, node.value))

			return result

		def bundler_version(self):
			node = self.lookup('BUNDLED WITH')
			if node is None:
				node = self.lookup('BUNDLED')
			if node is None or not node.children:
				return None
			node = node.children[0]
			return node.name

	# Process the output of "gem list", which contains lines like these:
	#	equalizer (0.0.11)
	#	etc (default: 1.0.0)
	#
	class GemList:
		class Package:
			def __init__(self, name = None):
				self.name = name
				self.versions = []

			def find(self, name):
				for node in self.children:
					if node.name == name:
						return node
				return None

			def __repr__(self):
				return ", ".join(self.versions)

			def dump(self, indent = ""):
				print("%s%s %s" % (indent, self.name, self.value))
				for node in self.children:
					node.dump(indent + "  ")

		def __init__(self):
			self.packages = dict()

		def dump(self):
			return self.node.dump()

		def add_package(self, name):
			pkg = self.packages.get(name)
			if pkg is None:
				pkg = self.Package(name)
				self.packages[name] = pkg

			return pkg

		@staticmethod
		def parse(f, ignore_defaults = True):
			import re

			result = Ruby.GemList()

			for l in f.readlines():
				l = l.strip()

				# parse identifier
				m = re.search('([^ ]*) *\((.*)\)', l)
				if not m:
					raise ValueError(l)

				name = m.group(1)
				pkg = result.add_package(name)

				rest = m.group(2)
				for version in rest.split(','):
					version = version.strip()
					if version.startswith("default:"):
						if ignore_defaults:
							continue

						version = version[8:].strip()

					pkg.versions.append(version)

			return result

		def package_set(self):
			return set(self.packages.keys())

		class ChangeSet:
			def __init__(self):
				self.added = []
				self.removed = []

			def add_to_list(self, list,  name, one_or_more_versions):
				if type(one_or_more_versions) == str:
					list.append("%s-%s" % (name, one_or_more_versions))
				else:
					for version in one_or_more_versions:
						list.append("%s-%s" % (name, version))

			def add_versions(self, *args):
				self.add_to_list(self.added, *args)

			def remove_versions(self, *args):
				self.add_to_list(self.removed, *args)

			def __bool__(self):
				return bool(self.added or self.removed)

			def show(self):
				if self.added:
					print("Added")
					for id in self.added:
						print("  " + id)

				if self.removed:
					print("Removed")
					for id in self.removed:
						print("  " + id)

		def changes(self, other):
			assert(isinstance(other, self.__class__))
			result = self.ChangeSet()

			our_names = self.package_set()
			her_names = other.package_set()

			for name in our_names - her_names:
				pkg = self.packages[name]
				result.remove_versions(name, pkg.versions)

			for name in her_names - our_names:
				pkg = other.packages[name]
				result.add_versions(name, pkg.versions)

			for name in our_names & her_names:
				our_versions = set(self.packages[name].versions)
				her_versions = set(other.packages[name].versions)
				result.remove_versions(name, our_versions - her_versions)
				result.add_versions(name, her_versions - our_versions)

			return result

class DecompressNone:
	@staticmethod
	def open(fileobj):
		return fileobj

class DecompressGzip:
	@staticmethod
	def open(fileobj):
		import gzip

		return gzip.GzipFile(fileobj = fileobj, mode = 'rb')

class DecompressZlib:
	@staticmethod
	def open(fileobj):
		import zlib
		import io

		data = zlib.decompress(fileobj.read())
		return io.BytesIO(data)

def guess_compression(url_or_path):
	if url_or_path.endswith(".gz"):
		return DecompressGzip
	if url_or_path.endswith(".rz"):
		return DecompressZlib
	return DecompressNone

def unmarshal(url_or_path, f = None, quiet = True):
	decompressor = guess_compression(url_or_path)
	if f is None:
		f = open(url_or_path, mode = 'rb')
	f = decompressor.open(f)

	return marshal48.unmarshal(f, Ruby.factory, quiet)

def unmarshal_byteseq(data, quiet = True):

	f = io.BytesIO(data)
	return marshal48.unmarshal(f, Ruby.factory, quiet)
