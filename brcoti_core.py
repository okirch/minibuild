#!/usr/bin/python3
#
# This is a simplistic build script for building artefacts of various
# programming languages natively (eg using pip, npm etc) and upload the
# resulting artefacts to a local repo.
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

def __pre_command():
	# Avoid messing up the order of our output and the output of subprocesses when
	# stdout is redirected
	sys.stdout.flush()
	sys.stderr.flush()

def run_command(cmd, ignore_exitcode = False):
	print("Running %s" % cmd)

	__pre_command()
	if os.system(cmd) != 0 and not ignore_exitcode:
		raise ValueError("Command `%s' returned non-zero exit status" % cmd)

def popen(cmd, mode = 'r'):
	print("Running %s" % cmd)

	__pre_command()
	return os.popen(cmd, mode)

class Object(object):
	def mni(self):
		import sys
		import traceback
		import threading

		my_thread = threading.current_thread()
		for thread, frame in sys._current_frames().items():
			if thread != my_thread.ident:
				continue

			if frame.f_code.co_name != 'mni':
				break

			frame = frame.f_back
			raise NotImplementedError("%s.%s(): method not implemented" % (self.__class__.__name__, frame.f_code.co_name))

		# we were trying to be too clever; or something changed in the way python handles stack frames.
		# Fall back to a more bland error message
		raise NotImplementedError("%s: method not implemented" % (self.__class__.__name__))

class PackageBuildInfo(Object):
	def __init__(self, name, version = None):
		self.name = name
		self.version = version

		self.url = None
		self.local_path = None

		self.hash = {}

	def id(self):
		self.nmi()

	def git_url(self):
		self.nmi()

	def get_hash(self, algo):
		return self.hash.get(algo)

	def add_hash(self, algo, md):
		# print("%s %s=%s" % (self.filename, algo, md))
		self.hash[algo] = md

	@property
	def is_source(self):
		self.nmi()

class PackageReleaseInfo(Object):
	def __init__(self, name, version):
		self.name = name
		self.version = version

		self.builds = []

	def id(self):
		self.nmi()

	def more_recent_than(self, other):
		self.nmi()

	def add_build(self, build):
		self.builds.append(build)

class PackageInfo(Object):
	def __init__(self, name):
		self.name = name
		self.releases = []

	def add_release(self, release):
		self.releases.append(release)

	def versions(self):
		return [r.version for r in self.releases]

class DownloadFinder(Object):
	def __init__(self, verbose):
		self.verbose = verbose

	def get_best_match(self, index):
		self.mni()

class PackageIndex(Object):
	def get_package_info(self, name):
		self.mni()

class HTTPPackageIndex(PackageIndex):
	def __init__(self, url):
		self.url = url
		self._pkg_url_template = None

	def get_package_info(self, name):
		import urllib.request

		url = self._pkg_url_template.format(index_url = self.url, pkg_name = name)

		resp = urllib.request.urlopen(url)
		if resp.status != 200:
			raise ValueError("Unable to get package info for %s: HTTP response %s (%s)" % (
					name, resp.status, resp.reason))

		return self.process_package_info(name, resp)

	# returns a PackageInfo object
	def process_package_info(self, name, http_resp):
		self.mni()

# For now, this is a very trivial downloader.
# This could be something much more complex that uses caches, OBS, yadda yadda
class Downloader(object):
	def __init__(self):
		pass

	def download(self, build, destdir = None):
		import urllib.request

		if build.local_path:
			return build.local_path

		assert(build.url)
		assert(build.filename)

		url = build.url
		resp = urllib.request.urlopen(url)
		if resp.status != 200:
			raise ValueError("Unable to download %s from %s (HTTP status %s %s)" % (
					build.filename, url, resp.status, resp.reason))

		filename = build.filename
		if destdir:
			filename = os.path.join(destdir, filename)

		with open(filename, "wb") as f:
			f.write(resp.read())

		print("Downloaded %s from %s" % (filename, url))

		build.local_path = filename
		return filename

# For now, a very trivial uploader.
class Uploader(Object):
	def __init__(self):
		pass

	def describe(self):
		self.mni()

	def upload(self, build):
		self.mni()

class BuildDirectory(Object):
	def __init__(self, compute, build_base):
		self.compute = compute
		self.build_base = self.compute.get_directory(build_base)
		self.directory = None
		self.sdist = None
		self.quiet = False

		self.artefacts = []

	def cleanup(self):
		if self.directory:
			self.directory.rmtree()

	@property
	def location(self):
		return self.build_base.path

	def unpacked_dir(self):
		if not self.directory:
			return "<none>"

		return self.directory.path

	def unpack_archive(self, sdist):
		archive = sdist.local_path
		if not archive or not os.path.exists(archive):
			raise ValueError("Unable to unpack %s: you need to download the archive first" % sdist.filename)

		relative_unpack_dir = self.archive_get_unpack_directory(sdist)

		d = self.build_base.lookup(relative_unpack_dir)
		if d is not None:
			d.rmtree()

		shutil.unpack_archive(archive, self.build_base.hostpath())

		self.directory = self.build_base.lookup(relative_unpack_dir)
		if not self.directory or not self.directory.isdir():
			raise ValueError("Unpacking %s failed: cannot find %s in %s" % (archive, relative_unpack_dir, self.build_base.path))

		self.sdist = sdist

	def unpack_git(self, sdist, destdir):
		repo_url = sdist.git_url()
		if not repo_url:
			raise ValueError("Unable to build from git - cannot determine git url")

		self.unpack_git_helper(repo_url, tag = sdist.version, destdir = sdist.id())
		self.sdist = sdist

	# General helper function: clone a git repo to the given destdir, and
	# optionally check out the tag requested (HEAD otherwise)
	def unpack_git_helper(self, git_repo, tag = None, destdir = None):
		assert(destdir) # for now

		if destdir:
			self.compute.run_command("git clone %s %s" % (git_repo, destdir))
		else:
			self.compute.run_command("git clone %s" % (git_repo))

		if tag:
			self.compute.run_command("git checkout %s" % tag, working_dir = destdir)

	def build(self, quiet = False):
		self.mni()

	def unchanged_from_previous_build(self, build_state):
		self.mni()

	def guess_build_dependencies(self):
		self.mni()

	def finalize_build_depdendencies(self, downloader):
		self.mni()

	def prepare_results(self, build_state):
		self.mni()

	def build_requires_as_string(self):
		self.mni()

	def unchanged_from_previous_build(self, build_state):
		if not build_state.exists():
			print("%s was never built before" % self.sdist.id())
			return False

		samesame = True
		for build in self.artefacts:
			artefact_name = os.path.basename(build.local_path)

			new_path = build.local_path
			old_path = build_state.get_old_path(artefact_name)
			print("Checking %s vs %s" % (new_path, old_path))
			if not os.path.exists(old_path):
				print("%s does not exist" % old_path)
				samesame = False
				continue

			if not self.artefacts_identical(old_path, new_path):
				print("%s differs from previous build" % artefact_name)
				samesame = False
				continue

		path = build_state.get_old_path("build-requires")
		if not os.path.exists(path):
			print("Previous build of %s did not write a build-requires file" % self.sdist.id())
			samesame = False
		else:
			new_path = build_state.get_new_path("build-requires")

			with open(path, "r") as old_f:
				with open(new_path, "r") as new_f:
					if old_f.read() != new_f.read():
						print("Build requirements changed")
						run_command("diff -u %s %s" % (path, new_path), ignore_exitcode = True)
						samesame = False

		return samesame

	def artefacts_identical(self, old_path, new_path):
		def print_delta(path, how, name_set):
			print("%s: %s %d file(s)" % (path, how, len(name_set)))
			for name in name_set:
				print("  %s" % name)

		added_set, removed_set, changed_set = self.compare_build_artefacts(old_path, new_path)

		samesame = True
		if added_set:
			print_delta(new_path, "added", added_set)
			samesame = False

		if removed_set:
			print_delta(new_path, "removed", removed_set)
			samesame = False

		if changed_set:
			print_delta(new_path, "changed", changed_set)
			samesame = False

		if samesame:
			print("%s: unchanged" % new_path)

		return samesame

class BuildState(Object):
	def __init__(self, savedir):
		import tempfile

		self.savedir = savedir
		self.tmpdir = tempfile.TemporaryDirectory(prefix = "brcoti-")

	def __del__(self):
		self.cleanup()

	def exists(self):
		return os.path.exists(self.savedir)

	def rebuild_required(self):
		self.mni()

	def commit(self):
		if not self.tmpdir:
			print("%s: changes already committed" % self.savedir)
			return

		# Clean up the savedir
		if os.path.exists(self.savedir):
			shutil.rmtree(self.savedir)
		os.makedirs(self.savedir, mode = 0o755)

		# And copy our data over it
		print("Committing build state to %s:" % self.savedir, end = ' ')
		for file in glob.glob(os.path.join(self.tmpdir.name, "*")):
			print(os.path.basename(file), end = ' ')
			shutil.copy(file, self.savedir)
		print("")

	def cleanup(self):
		if self.tmpdir:
			del self.tmpdir
		self.tmpdir = None

	def get_old_path(self, name):
		return os.path.join(self.savedir, name)

	def get_new_path(self, name):
		return os.path.join(self.tmpdir.name, name)

	def maybe_save_file(self, src, dst = None):
		if not os.path.exists(src):
			print("Not saving %s (does not exist)" % src)
			return None

		return self.save_file(src, dst)

	def save_file(self, src):
		if isinstance(src, ComputeResourceFS):
			src = src.hostpath()
		dst = self.tmpdir.name

		print("Saving %s to %s" % (src, dst))
		shutil.copy(src, dst)

		if os.path.isdir(dst):
			return os.path.join(dst, os.path.basename(src))
		return dst

	def write_file(self, name, data, desc = None):
		path = os.path.join(self.tmpdir.name, name)

		if desc:
			print("Writing %s to %s" % (desc, path))
		else:
			print("Writing %s" % path)
		with open(path, "w") as f:
			f.write(data)

	def rebuild_required(self):
		path = self.get_old_path("build-artefacts")
		if not os.path.exists(path):
			print("Previous build did not create build-artefacts file")
			return True

		path = self.get_old_path("build-requires")
		if not os.path.exists(path):
			print("Previous build did not create build-requires file")
			return True

		try:
			req_list = self.parse_build_requires(path)
		except Exception as e:
			print("Cannot parse build-requires file at %s" % path)
			print(e)
			return True

		for req in req_list:
			if self.build_changed(req):
				return True

			print("Build requirement %s did not change" % req.id())

		return False

	def parse_build_requires(self, path):
		result = []

		with open(path, 'r') as f:
			req = None
			for l in f.readlines():
				if not l:
					continue

				if l.startswith("require"):
					name = l[7:].strip()
					req = self.create_empty_requires(name)
					result.append(req)
					continue

				if req is None:
					raise ValueError("%s: no build info in this context" % (path, ))

				if l.startswith(' '):
					words = l.strip().split()
					if not words:
						continue
					if words[0] == 'specifier':
						req.fullreq = " ".join(words[1:])
						continue

					if words[0] == 'hash':
						req.add_hash(words[1], words[2])
						continue

				raise ValueError("%s: unparseable line <%s>" % (path, l))

		return result

	def create_empty_requires(self, name):
		self.mni()

class ComputeResourceFS(Object):
	def __init__(self, path):
		self.path = path

	def basename(self):
		return os.path.basename(self.path)

	def rmtree(self):
		path = self.hostpath()
		if os.path.exists(path):
			print("Recursively remove %s" % path)
			shutil.rmtree(path)

	def hostpath(self):
		self.mni()

class ComputeResourceFile(ComputeResourceFS):
	def __init__(self, path):
		super(ComputeResourceFile, self).__init__(path)

	def open(self, mode = 'r'):
		self.mni()

	def isreg(self):
		return True

	def isdir(self):
		return False

class ComputeResourceDirectory(ComputeResourceFS):
	def __init__(self, path):
		super(ComputeResourceDirectory, self).__init__(path)

	def file_exists(self, path):
		self.mni()

	def lookup(self, path):
		self.mni()

	def open(self, path, mode = 'r'):
		self.mni()

	def glob_files(self, path_pattern):
		self.mni()

	def isreg(self):
		return False

	def isdir(self):
		return True

class ComputeNode(Object):
	def __init__(self):
		pass

	def run_command(self, cmd, working_dir = None, ignore_exitcode = False):
		if not working_dir:
			print("Running %s" % cmd)
		else:
			print("Running %s [in directory %s]" % (cmd, working_dir))

		# Avoid messing up the order of our output and the output of subprocesses when
		# stdout is redirected
		sys.stdout.flush()
		sys.stderr.flush()

		exit_code = self._run_command(cmd, working_dir)

		if exit_code != 0 and not ignore_exitcode:
			raise ValueError("Command `%s' returned non-zero exit status" % cmd)

		return exit_code

	def _run_commandx(self, cmd, working_dir = None):
		self.mni()

	def popen(self, cmd, mode = 'r'):
		print("Running %s" % cmd)

		# Avoid messing up the order of our output and the output of subprocesses when
		# stdout is redirected
		sys.stdout.flush()
		sys.stderr.flush()

		return self._popen(cmd, mode)

	def _popen(self, cmd, mode):
		self.mni()

	def get_directory(self, path):
		self.mni()

	def shutdown(self):
		self.mni()


class Compute(Object):
	def spawn(self, flavor):
		self.mni()

	@staticmethod
	def factory(name, opts):
		print("Create %s compute backend" % name)
		if name == 'local':
			import brcoti_local

			return brcoti_local.compute_factory(opts)

		raise NotImplementedError("No compute backend for \"%s\"" % name)

class Engine(Object):
	def __init__(self, name, compute, opts):
		self.name = name
		self.compute = compute

		self.state_dir = opts.output_dir
		self.build_dir = "BUILD"

		self.downloader = None
		self.uploader = None

	def prepare_environment(self):
		# This is a no-op by default
		pass

	def downloader(self):
		return Downloader()

	def uploader(self):
		self.mni()

	def build_info_from_local_file(self, path):
		self.mni()

	def build_source_locate(self, req_string, verbose = True):
		self.mni()

	def build_state_factory(self, sdist):
		self.mni()

	def build_state_path(self, artefact_name):
		return os.path.join(self.state_dir, artefact_name)

	def build_unpack(self, sdist):
		self.mni()

	def finalize_build_depdendencies(self, build):
		tempdir = None
		for req in build.build_requires:
			missing = []
			for algo in self.REQUIRED_HASHES:
				if req.get_hash(algo) is None:
					missing.append(algo)

			if not missing:
				continue

			print("%s: update missing hash(es): %s" % (req.id(), " ".join(missing)))

			if not tempdir:
				import tempfile

				tempdir = tempfile.TemporaryDirectory(prefix = "build-deps-")

			if req.url is not None:
				self.downloader.download(req, tempdir.name)
				for algo in missing:
					req.update_hash(algo)
			else:
				resolved_req = self.resolve_build_req(req)
				if not resolved_req:
					raise ValueError("Unable to resolve build dependency %s" % req.name)
				self.downloader.download(resolved_req, tempdir.name)

				for algo in missing:
					resolved_req.update_hash(algo)
					req.add_hash(algo, resolved_req.hash[algo])

		if tempdir:
			tempdir.cleanup()


	def resolve_build_req(self, req):
		self.mni()

	@staticmethod
	def factory(compute, name, opts):
		print("Create %s engine" % name)
		if name == 'python':
			import brcoti_python

			return brcoti_python.engine_factory(compute, opts)

		if name == 'ruby':
			import brcoti_ruby

			return brcoti_ruby.engine_factory(compute, opts)

		raise NotImplementedError("No build engine for \"%s\"" % name)
