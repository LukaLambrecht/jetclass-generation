// main03.cc is a part of the PYTHIA event generator.
// Copyright (C) 2021 Torbjorn Sjostrand.
// PYTHIA is licenced under the GNU GPL v2 or later, see COPYING for details.
// Please respect the MCnet Guidelines, see GUIDELINES for details.

// Adapted from Pythia's main03 example: generate events from the settings in
// py8.dat and write them to events.hepmc. Used for the Pythia-only processes,
// which have no MadGraph step.

#include "Pythia8/Pythia.h"
#include "Pythia8Plugins/HepMC2.h"

using namespace Pythia8;

//==========================================================================

// Read py8.dat, generate Main:numberOfEvents events and stream each one to
// events.hepmc. Aborts early if the generator fails too often.
int main() {

  Pythia8ToHepMC toHepMC("events.hepmc");

  // Generator.
  Pythia pythia;

  // Shorthand for the event record in pythia.
  Event& event = pythia.event;

  // Read in commands from external file.
  pythia.readFile("py8.dat");

  // Extract settings to be used in the main program.
  int nEvent = pythia.mode("Main:numberOfEvents");
  int nAbort = pythia.mode("Main:timesAllowErrors");

  // Initialize.
  pythia.init();

  // Begin event loop.
  int iAbort = 0;
  for (int iEvent = 0; iEvent < nEvent; ++iEvent) {

    // Generate events. Quit if many failures.
    if (!pythia.next()) {
      if (++iAbort < nAbort) continue;
      cout << " Event generation aborted prematurely, owing to error!\n";
      break;
    }
    toHepMC.writeNextEvent( pythia );
  // End of event loop.
  }

  // Final statistics. Normalize and output histograms.
  pythia.stat();

  // Done.
  return 0;
}
