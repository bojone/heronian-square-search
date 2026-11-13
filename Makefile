CXX ?= g++
NVCC ?= nvcc
CXXFLAGS ?= -O3 -std=c++17 -Wall -Wextra -march=native
CUDAFLAGS ?= -O3 -std=c++17
GPU_ARCH ?= native

.PHONY: all cpu gpu test test-cpu clean

all: cpu gpu

cpu: search search_v13

gpu: gpu_search_v42

build:
	mkdir -p build

build/search: src/search_v18.cpp | build
	$(CXX) $(CXXFLAGS) -pthread $< -o $@

search: build/search
	ln -sf build/search $@

search_v13: search
	ln -sf search $@

build/gpu_search_v42: src/gpu_search_v42.cu | build
	$(NVCC) $(CUDAFLAGS) -arch=$(GPU_ARCH) $< -o $@

gpu_search_v42: build/gpu_search_v42
	ln -sf build/gpu_search_v42 $@

test: all
	python3 scripts/smoke_test.py --search search --gpu-search gpu_search_v42
	python3 scripts/verify_all_results.py --root evidence --known-only

test-cpu: cpu
	python3 scripts/smoke_test.py --search search --skip-gpu
	python3 scripts/verify_all_results.py --root evidence --known-only

clean:
	rm -rf build search search_v13 gpu_search_v42
