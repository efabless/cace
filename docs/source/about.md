# About

CACE is a set of python scripts that take an input file in the
[CACE 4.0 format](formats/format_description) and uses the information found there in combination with CACE-compatible testbenches and analysis scripts to characterize a circuit and to produce a datasheet showing the circuit performance.  The CACE python code is the part of CACE which is common to all circuit designs.

The CACE python code does the following:

1. Reads the specification input file
2. Determines how many simulations will need to be run for each electrical parameter
3. Generates testbench templates from schematics
4. Substitutes values for all parameters for each simulation
5. Generates the circuit netlist to be tested (either pre-layout or post-layout)
6. Runs simulations in parallel
7. Runs additional scripts to analyze specific performance metrics, as specified in the input file
8. Collates results and generates pass/fail results for all electrical parameters
9. Generates graphs of results as specified in the input file 
10. Runs additional measurements for DRC, LVS, and physical dimensions as specified in the input file
11. Collates results and generates pass/fail results for all physical parameters

By necessity, every circuit will have its own set of testbench
schematics, which no common code system can automatically generate, as every test bench will be specific to the circuit design. Certain general principles apply, and are covered by a number of example circuits available on github;  each of these designs has a "cace/" directory containing the specification, testbench schematics, and any additional code needed to analyze the results.

The CACE input file describes the specification for the circuit in terms of electrical and physical parameters that need to be measured and analyzed.  After simulation, a copy of the file is produced containing measured results and providing a pass/fail result for each parameter.
