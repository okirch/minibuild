#
# rubygem specific portions of brcoti
#
#   Copyright (C) 2020 Olaf Kirch <okir@suse.de>
#
#   This program is free software; you can redistribute it and/or modify
#   it under the terms of the GNU General Public License as published by
#   the Free Software Foundation; either version 2 of the License, or
#   (at your option) any later version.
#
#   This program is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#   GNU General Public License for more details.
#
#   You should have received a copy of the GNU General Public License
#   along with this program; if not, write to the Free Software
#   Foundation, Inc., 675 Mass Ave, Cambridge, MA 02139, USA.
#

import sys
import os
import os.path
import io
import glob
import shutil
import ruby_utils

import brcoti_core

def get_ruby_version():
	return os.popen("ruby -e 'print(RUBY_VERSION)'").read()

def get_rubygems_version():
	return os.popen("ruby -e 'print(Gem::VERSION)'").read()

def canonical_package_name(name):
	return name

class RubyBuildInfo(brcoti_core.PackageBuildInfo):
	def __init__(self, name, version = None, type = None):
		super(RubyBuildInfo, self).__init__(canonical_package_name(name), version)

		self.type = type
		self.required_ruby_version = None
		self.required_rubygems_version = None

		self.fullreq = None
		self.cooked_requirement = None

		self.filename = None

		# package info
		self.home_page = None
		self.author = None

	def id(self):
		if not self.version:
			return self.name
		return "%s-%s" % (self.name, self.version)

	def update_hash(self, algo):
		import hashlib

		m = hashlib.new(algo)
		with open(self.local_path, "rb") as f:
			m.update(f.read())

		self.add_hash(algo, m.hexdigest())

	def git_url(self):
		url = self.home_page
		if not url:
			return None

		url = url.replace('_', '-')
		if not url or not "github.com" in url:
			print("WARNING: Package homepage \"%s\" doesn't look like a git repo" % url)
			return None

		return url

	@property
	def is_source(self):
		return self.type == 'source'

	def verify_minimum_version(self, my_version, req_version):
		import ruby_utils

		if req_version is None:
			return True

		# print("verify_minimum_version(mine=%s, wanted=%s)" % (my_version, req_version))
		return my_version in req_version

	def verify_required_ruby_version(self):
		return self.verify_minimum_version(get_ruby_version(), self.required_ruby_version)

	def verify_required_rubygems_version(self):
		return self.verify_minimum_version(get_rubygems_version(), self.required_rubygems_version)

	@staticmethod
	def parse_filename(filename):
		def split_suffix(name):
			if name.endswith(".tar.gz"):
				k = -7
			elif name.endswith(".tar.bz2"):
				k = -8
			else:
				k = name.rindex('.')
			suffix = name[k+1:]
			name = name[:k]
			return name, suffix

		def split_version(name):
			components = name.split('-')
			nlist = []
			while components:
				c = components[0]
				if c[0].isdigit():
					break
				nlist.append(c)
				del components[0]

			name = "-".join(nlist)
			version = "-".join(components)
			return name, version

		# First, separate the suffix from the file name
		_name, _suffix = split_suffix(filename)

		# Then, split the name into package name and version.
		# Things get a bit hairy because we need to deal with
		# weirdo names like jedi-0.8.0-final0
		_name, _version = split_version(_name)

		if _suffix in ("tar.gz", "tar.bz2", "zip"):
			_type = 'source'
		elif _suffix == "gem":
			_type = 'gem'
		else:
			raise ValueError("Unable to parse file name \"%s\"" % filename)

		return _name, _version, _type

	@staticmethod
	def from_local_file(path, name = None, version = None, type = None):
		filename = os.path.basename(path)

		if not name or not version or not type:
			# try to detect version and type by looking at the file name
			_name, _version, _type = RubyBuildInfo.parse_filename(filename)

			if name:
				assert(name == _name)
			name = _name
			if version:
				assert(version == _version)
			version = _version
			if type:
				assert(type == _type)
			type = _type

		build = RubyBuildInfo(name, version, type)
		build.filename = filename
		build.local_path = path

		for algo in RubyEngine.REQUIRED_HASHES:
			build.update_hash(algo)

		return build

class RubyReleaseInfo(brcoti_core.PackageReleaseInfo):
	def __init__(self, name, version, parsed_version = None):
		super(RubyReleaseInfo, self).__init__(canonical_package_name(name), version)

		if not parsed_version:
			parsed_version = ruby_utils.Ruby.ParsedVersion(version)

		self.parsed_version = parsed_version

	def id(self):
		return "%s-%s" % (self.name, self.version)

	def more_recent_than(self, other):
		assert(isinstance(other, RubyReleaseInfo))
		return other.parsed_version < this.parsed_version

	def build_types(self):
		return [b.type for b in self.builds]

class RubyPackageInfo(brcoti_core.PackageInfo):
	def __init__(self, name):
		super(RubyPackageInfo, self).__init__(canonical_package_name(name))

class RubyDownloadFinder(brcoti_core.DownloadFinder):
	def __init__(self, req_string, verbose, cooked_requirement = None):
		from packaging.requirements import Requirement

		super(RubyDownloadFinder, self).__init__(verbose)
		if not cooked_requirement:
			import ruby_utils

			cooked_requirement = ruby_utils.Ruby.parse_dependency(req_string)

		self.requirement = cooked_requirement
		self.name = cooked_requirement.name
		self.allow_prereleases = False

	def release_match(self, release):
		assert(release.parsed_version)
		if not self.allow_prereleases and release.parsed_version.is_prerelease:
			return False

		if (release.name, release.parsed_version) not in self.requirement:
			return False

		return True

	def get_best_match(self, index):
		info = index.get_package_info(self.name)

		if info is None:
			if self.verbose:
				print("%s not found in package index" % self.name)
			return None

		if self.verbose:
			print("%s versions: %s" % (self.name, ", ".join(info.versions())))

		best_ver = None
		best_match = None

		for release in info.releases:
			if not self.release_match(release):
				if self.verbose:
					print("ignoring release %s" % release.id())
				continue

			if best_ver and release.parsed_version <= best_ver:
				continue

			for build in release.builds:
				print("%s: inspecting build %s (type %s)" % (release.id(), build.filename, build.type))
				if self.build_match(build):
					if not build.verify_required_ruby_version():
						if self.verbose:
							print("ignoring build %s (requires ruby %s)" % (build.filename, build.required_ruby_version))
						continue

					if not build.verify_required_rubygems_version():
						if self.verbose:
							print("ignoring build %s (requires ruby gems %s)" % (build.filename, build.required_rubygems_version))
						continue

					best_match = build
					best_ver = release.parsed_version

		if not best_match:
			raise ValueError("%s: unable to find a matching release" % self.name)

		if self.verbose:
			print("Using %s" % best_match.id())

		return best_match

class RubySourceDownloadFinder(RubyDownloadFinder):
	def __init__(self, req_string, verbose = False, cooked_requirement = None):
		super(RubySourceDownloadFinder, self).__init__(req_string, verbose, cooked_requirement)

	def build_match(self, build):
		if self.verbose:
			print("inspecting %s which is of type %s" % (build.filename, build.type))
		return build.type == 'source'

class RubyBinaryDownloadFinder(RubyDownloadFinder):
	def __init__(self, req_string, verbose = False, cooked_requirement = None):
		super(RubyBinaryDownloadFinder, self).__init__(req_string, verbose, cooked_requirement)

	def build_match(self, build):
		if self.verbose:
			print("inspecting %s which is of type %s" % (build.filename, build.type))
		return build.type == 'gem'

class RubySpecIndex(brcoti_core.HTTPPackageIndex):
	def __init__(self, url):
		super(RubySpecIndex, self).__init__(url)

		# For some bizarre reason, the specs files are avaliable from nexus in different compression
		# formats, but the gemspec is only provided as zlib compressed file
		self._pkg_url_template = "{index_url}/quick/Marshal.4.8/{pkg_name}-{pkg_version}.gemspec.rz"

		self._cached_latest_specs = None

	def get_package_info(self, name):
		pi = self.locate_gem(name)

		for ri in pi.releases:
			self.get_gemspec(ri)

		return pi

	def locate_gem(self, name):
		# latest_specs.4.8 and specs.4.8 contain an array of info tuples.
		# Each tuple represents the (latest known) version of a gem, and consists of 3 elements:
		#  [name, Gem::Version(...), platform]
		# platform is usually "ruby", but can also be "java-something"
		gem_list = self._latest_specs()

		print("Locating %s in %s/latest_specs" % (name, self.url))
		version = None
		for gem in gem_list:
			if gem[0] == name:
				version_list = gem[1]
				# weird. rubygems.org always gives us an array of versions,
				# but nexus seems to give us a single version object
				if isinstance(version_list, ruby_utils.Ruby.GemVersion):
					version = str(version_list)
				else:
					version = version_list[0]
				if gem[2] != 'ruby':
					raise ValueError("Cannot use %s-%s: platform is \"%s\"" % (name, version, gem[2]))
				break

		if not version:
			raise ValueError("Gem \"%s\" not found in index" % name)

		pi = RubyPackageInfo(name)
		release = RubyReleaseInfo(name, version)
		pi.add_release(release)

		return pi

	def _latest_specs(self):
		if self._cached_latest_specs is None:
			self._cached_latest_specs = self._download_and_parse_specs("latest_specs.4.8.gz")
		return self._cached_latest_specs

	def _download_and_parse_specs(self, filename):
		import urllib.request

		url = self.url + "/" + filename

		resp = urllib.request.urlopen(url)
		if resp.status != 200:
			raise ValueError("Unable to download index %s: HTTP response %s (%s)" % (
					filename, resp.status, resp.reason))

		from ruby_utils import unmarshal

		# This is fairly slow... need to speed this up!
		return unmarshal(filename, resp)

	def get_gemspec(self, release):
		import urllib.request

		url = self._pkg_url_template.format(index_url = self.url, pkg_name = release.name, pkg_version = release.version)

		resp = urllib.request.urlopen(url)
		if resp.status != 200:
			raise ValueError("Unable to get package info for %s-%s: HTTP response %s (%s)" % (
					release.name, release.version, resp.status, resp.reason))

		self.process_gemspec_response(resp, release)

	def process_gemspec_response(self, resp, release):
		from ruby_utils import unmarshal

		gemspec = unmarshal(resp.url, resp)

		release.add_build(self.gemspec_to_binary(gemspec))

		build = self.gemspec_to_source(gemspec)
		if build:
			release.add_build(build)

	def gemspec_to_binary(self, gemspec):
		build = self.gemspec_to_build_common(gemspec, 'gem')

		build.filename = "%s-%s.gem" % (gemspec.name, gemspec.version)
		build.url = "%s/gems/%s" % (self.url, build.filename)
		return build

	def gemspec_to_source(self, gemspec):
		for url in (gemspec.homepage, gemspec.unknown3):
			# source tarballs for eg sprockets-rails can be found at
			# https://github.com/rails/sprockets-rails/archive/v${version}.tar.gz
			if url.startswith('https://github.com/'):
				url = "%s/archive/v%s.tar.gz" % (url, gemspec.version)
				if self.uri_exists(url):
					build = self.gemspec_to_build_common(gemspec, 'source')
					build.filename = "%s-%s.tar.gz" % (gemspec.name, gemspec.version)
					build.url = url
					return build

		return None

	def gemspec_to_build_common(self, gemspec, build_type):
		build = RubyBuildInfo(gemspec.name, gemspec.version, type = build_type)
		build.required_ruby_version = gemspec.required_ruby_version
		build.required_rubygems_version = gemspec.required_rubygems_version

		build.filename = "%s-%s.gem" % (gemspec.name, gemspec.version)
		build.url = "%s/gems/%s" % (self.url, build.filename)

		build.author = gemspec.author
		build.homepage = gemspec.homepage

		if False:
			for attr_name in dir(gemspec):
				attr_val = getattr(gemspec, attr_name)
				if callable(attr_val) or attr_name.startswith('_'):
					continue
				print("%-20s = %s" % (attr_name, attr_val))

			for key, value in gemspec.metadata.items():
				print("metadata." + key, value)

		build.gemspec = gemspec
		return build

	def uri_exists(self, url):
		import urllib.request

		req = urllib.request.Request(url=url, method='HEAD')
		resp = urllib.request.urlopen(req)

		return resp.status == 200

# Upload package using "gem nexus"
# You need to have the nexus gem installed for this
class RubyUploader(brcoti_core.Uploader):
	def __init__(self, url, user, password):
		self.url = url
		self.config_written = False

		assert(user)
		assert(password)

		self.user = user
		self.password = password

	def describe(self):
		return "Ruby repository \"%s\"" % self.url

	def upload(self, build):
		assert(build.local_path)

		self.prepare_config()

		print("Uploading %s to %s repository" % (build.local_path, self.url))
		brcoti_core.run_command("gem nexus %s" % build.local_path)

	def prepare_config(self):
		if not self.config_written:
			import basicauth

			home = os.getenv("HOME")
			assert(home)
			path = os.path.join(home, ".gem", "nexus")

			with open(path, "w") as f:
				f.writelines("---\n:url: %s\n:authorization: %s\n" % (
					self.url,
					basicauth.encode(self.user, self.password)))

			self.config_written = True

class GemFile(object):
	def __init__(self, path):
		self.path = path

		self._tar = self.open()

	def open(self):
		import tarfile

		return tarfile.open(self.path, mode = 'r')

	@property
	def basename(self):
		return os.path.basename(self.path)

	def compare(self, other):
		return GemFile.do_compare(self, other)
	
	@staticmethod
	def do_compare(old, new):
		# First, compare the contents of data.tar.gz.
		# We only look at regular files contained in the tarfile, even though
		# we should probably also look at symlinks and hardlinks
		added_set, removed_set, changed_set = GemFile.compare_data(old, new)

		if old.get_metadata() != new.get_metadata():
			changed_set.add("metadata.gz")

		# Ignore checksums.yaml

		return added_set, removed_set, changed_set

	@staticmethod
	def compare_data(old, new):
		old_data_tar = old.get_data()
		new_data_tar = new.get_data()

		old_name_set = GemFile.tar_member_names(old_data_tar)
		new_name_set = GemFile.tar_member_names(new_data_tar)

		added_set = new_name_set - old_name_set
		removed_set = old_name_set - new_name_set

		changed_set = set()
		for member_name in old_name_set.intersection(new_name_set):
			old_data = GemFile.get_member_data(old_data_tar, member_name)
			new_data = GemFile.get_member_data(new_data_tar, member_name)

			if new_data != old_data:
				changed_set.add(member_name)

		if False:
			print("added=" + ", ".join(added_set))
			print("removed=" + ", ".join(removed_set))
			print("changed=" + ", ".join(changed_set))

		return added_set, removed_set, changed_set

	def get_data(self):
		import tarfile

		try:
			f = self._tar.extractfile("data.tar.gz")
		except:
			print("ERROR: %s does not contain data.tar.gz" % self.path)
			# Forces a mis-compare in the caller
			return self.path

		return tarfile.open(fileobj = f, mode = 'r:gz')

	@staticmethod
	def tar_member_names(tar_file):
		result = set()
		for member in tar_file.getmembers():
			if member.isfile():
				result.add(member.name)

		return result

	@staticmethod
	def get_member_data(tar_file, name):
		return tar_file.extractfile(name).read()

	def get_metadata(self):
		import gzip

		try:
			f = self._tar.extractfile("metadata.gz")
		except:
			print("ERROR: %s does not contain metadata.gz" % self.path)
			# Forces a mis-compare in the caller
			return self.path

		f = gzip.GzipFile(fileobj = f, mode = 'r')
		return f.read()

class RubyBuildDirectory(brcoti_core.BuildDirectory):
	def __init__(self, compute, build_base):
		super(RubyBuildDirectory, self).__init__(compute, build_base)

	# Most of the unpacking happens in the BuildDirectory base class.
	# The only python specific piece is guessing which directory an archive is extracted to
	def archive_get_unpack_directory(self, sdist):
		name, version, type = RubyBuildInfo.parse_filename(sdist.local_path)
		return name + "-" + version

	def unpack_git(self, sdist, destdir):
		repo_url = sdist.git_url()
		if not repo_url:
			raise ValueError("Unable to build from git - cannot determine git url")

		self.unpack_git_helper(repo_url, tag = sdist.version, destdir = sdist.id())

		self.sdist = sdist

	def build(self):
		assert(self.directory)
		sdist = self.sdist

		cmd = "gem build " + sdist.name

		# build.log is a host-side file. Which is why we rely
		# on the caller to give us its full path through a call to set_logging()
		if self.quiet:
			if self.build_log is not None:
				cmd += " >%s 2>&1" % self.build_log
			else:
				cmd += " >/dev/null 2>&1"
		elif self.build_log:
			cmd += " 2>&1 | tee %s" % self.build_log

		self.compute.run_command(cmd, working_dir = self.directory)

		gems = self.directory.glob_files("*.gem")

		print("Successfully built %s: %s" % (sdist.id(), ", ".join([w.basename() for w in gems])))
		for w in gems:
			w = w.hostpath()

			build = RubyBuildInfo.from_local_file(w)

			for algo in RubyEngine.REQUIRED_HASHES:
				build.update_hash(algo)

			self.artefacts.append(build)

		return self.artefacts

	# Compare old build of a gem vs the current build. This method
	# is expected to return three set objects:
	# added_set, removed_set, changed_set
	def compare_build_artefacts(self, old_path, new_path):
		return GemFile(old_path).compare(GemFile(new_path))

	# It would be better if we'd inspect the build log for the actual artefacts
	# used, rather than going through the spec index ourselves. However, for the
	# time being I don't know where to actually get this info from
	def guess_build_dependencies(self):
		from packaging.requirements import Requirement
		import re

		self.build_requires = []

		gemspec = self.sdist.gemspec
		for dep in gemspec.dependencies:
			if dep.type != 'development':
				continue
			req = RubyBuildInfo(dep.name, type = "gem")
			req.fullreq = req.name + ",".join([str(x) for x in dep.requirement])
			req.cooked_requirement = dep

			self.build_requires.append(req)
		return

	def prepare_results(self, build_state):
		build_state.write_file("build-requires", self.build_requires_as_string())
		build_state.write_file("build-artefacts", self.build_artefacts_as_string())

		for build in self.artefacts:
			build.local_path = build_state.save_file(build.local_path)

	def build_artefacts_as_string(self):
		b = io.StringIO()
		for build in self.artefacts:
			b.write("gem %s\n" % build.name)
			b.write("  version %s\n" % build.version)

			for algo in RubyEngine.REQUIRED_HASHES:
				b.write("  hash %s %s\n" % (algo, build.get_hash(algo)))
		return b.getvalue()

	def build_requires_as_string(self):
		b = io.StringIO()
		for req in self.build_requires:
			b.write("require %s\n" % req.name)

			req_string = None
			if req.cooked_requirement:
				req_string = req.cooked_requirement.format()
			elif req.fullreq:
				req_string = req.fullreq
			if req_string:
				b.write("  specifier %s\n" % req_string)
			if req.hash:
				for (algo, md) in req.hash.items():
					b.write("  hash %s %s\n" % (algo, md))
		return b.getvalue()

	def maybe_save_file(self, build_state, name):
		fh = self.directory.lookup(name)
		if fh is None:
			print("Not saving %s (does not exist)" % name)
			return None

		return build_state.save_file(fh)

	def write_file(self, build_state, name, write_func):
		buffer = io.StringIO()
		write_func(buffer)
		return build_state.write_file(name, buffer.getvalue())

class RubyBuildState(brcoti_core.BuildState):
	def __init__(self, savedir, index):
		super(RubyBuildState, self).__init__(savedir)

		self.index = index

	def build_changed(self, req):
		if req.fullreq:
			finder = RubyBinaryDownloadFinder(req.fullreq)
		else:
			finder = RubyBinaryDownloadFinder(req.name)

		print("Build requires %s" % (finder.requirement))

		p = finder.get_best_match(self.index)

		print("  Best match available from package index: %s" % p.filename)
		if req.version:
			if req.version != p.version:
				print("Building would pick %s-%s rather than %s-%s" % (
					p.name, p.version,
					req.name, req.version))
				return True

		match = False
		for algo, md in req.hash.items():
			print("  We are looking for %s %s %s" % (req.id(), algo, md))
			have_md = p.hash.get(algo)
			if have_md is None:
				print("  => index does not provide %s hash for %s" % (algo, p.filename))
				continue

			print("  => index provides %s %s %s" % (p.filename, algo, p.hash.get(algo)))
			if have_md == md:
				match = True

		if not match:
			print("%s was apparently rebuilt in the meantime, we need to rebuild" % p.filename)
			return True

		print("Build requirement did not change")

	def create_empty_requires(self, name):
		return RubyBuildInfo(name)

class RubyEngine(brcoti_core.Engine):
	REQUIRED_HASHES = ('md5', 'sha256')

	def __init__(self, compute_backend, opts):
		compute = compute_backend.spawn("ruby")

		super(RubyEngine, self).__init__("ruby", compute, opts)

		self.index_url = 'http://localhost:8081/repository/ruby-group/'
		self.index = RubySpecIndex(url = self.index_url)

		self.prefer_git = opts.git

		self.downloader = brcoti_core.Downloader()

		if opts.upload_to:
			url = self.index_url.replace("/ruby-group", "/ruby-" + opts.upload_to)
			self.uploader = RubyUploader(url, user = opts.repo_user, password = opts.repo_password)

	def prepare_environment(self):
		urls = []
		need_to_add = False

		with self.compute.popen("gem sources --list") as f:
			for l in f.readlines():
				l = l.strip()
				if l == self.index_url:
					need_to_add = False
				elif l.startswith("http"):
					urls.append(l)
		for url in urls:
			self.compute.run_command("gem sources --remove %s" % url)
		if need_to_add:
			self.compute.run_command("gem sources --add %s" % self.index_url)

	def build_info_from_local_file(self, path):
		return RubyBuildInfo.from_local_file(path)

	def build_source_locate(self, req_string, verbose = False):
		finder = RubySourceDownloadFinder(req_string, verbose)
		return finder.get_best_match(self.index)

	def build_state_factory(self, sdist):
		savedir = self.build_state_path(sdist.id())
		return RubyBuildState(savedir, self.index)

	def build_unpack(self, sdist):
		bd = RubyBuildDirectory(self.compute, self.build_dir)
		if self.prefer_git:
			bd.unpack_git(sdist, sdist.id())
		else:
			bd.unpack_archive(sdist)

		print("Unpacked %s to %s" % (sdist.id(), bd.unpacked_dir()))
		return bd

	def resolve_build_req(self, req):
		assert(req.cooked_requirement)
		dep = req.cooked_requirement

		finder = RubyBinaryDownloadFinder(req.fullreq, cooked_requirement = req.cooked_requirement)
		return finder.get_best_match(self.index)

def engine_factory(compute, opts):
	return RubyEngine(compute, opts)
