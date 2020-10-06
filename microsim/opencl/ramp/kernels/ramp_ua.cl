#include "prng.cl"

/*
This file contains all the OpenCL kernel logic for the RAMP Urban Analytics Covid-19 model.
*/

/*
  Constants
*/

// sentinel value to indicate empty slots 
constant uint sentinel_value = ((uint)1<<31) - 1;

// Fixed point precision factor. This needs to be big enough to represent sufficiently
// small numbers (anything less than 1 / fixed_factor rounds to 0) and small enough to
// prevent overflow (anything greater than max_uint / fixed_factor will overflow).
// A good choice depends on the use, here we're mainly representing probabilities so
// this value is chosen since it matches the set of values in the unit interval
// representable by a floating point number with a fixed exponent and 23 bit significand.
constant float fixed_factor = 8388608.0;

/*
  Disease Status Enum
*/
typedef enum DiseaseStatus {
  Susceptible = 0,
  Exposed = 1,
  Presymptomatic = 2,
  Asymptomatic = 3,
  Symptomatic = 4,
  Recovered = 5,
  Dead = 6,
} DiseaseStatus;

bool is_infectious(DiseaseStatus status) {
  return status == Presymptomatic || status == Asymptomatic || status == Symptomatic;
}

/*
  Activity type enum
*/
typedef enum Activity {
  Home = 0,
  Retail = 1,
  PrimarySchool = 2,
  SecondarySchool = 3,
  Work = 4,
} Activity;


/*
  Model parameters
*/
typedef struct Params {
  float symptomatic_multiplier; // Increase in time at home if symptomatic
  float proportion_asymptomatic; // Proportion of cases that are asymptomatic
  float exposed_scale; // The scale of the distribution of exposed durations
  float exposed_shape; // The shape of the distribution of exposed durations
  float presymp_scale; // The scale of the distribution of presymptomatic durations
  float presymp_shape; // The shape of the distribution of presymptomatic durations
  float infection_scale; // The scale of the distribution of infected durations
  float infection_loc; // The location of the distribution of infected durations
  float lockdown_multiplier; // Increase in time at home due to lockdown
  float place_hazard_multipliers[5]; // Hazard multipliers by activity
  float recovery_probs[9]; // Recovery probabilities by age group
} Params;

/*
  Utility functions
*/

// get the corresponding 1D index for a 2D index 
int get_1d_index(int person_id, int slot, int nslots) {
  return person_id*nslots + slot;
}

uint sample_exposed_duration(global uint4* rng, global const Params* params){
  return (uint)rand_weibull(rng, params->exposed_scale, params->exposed_shape);
}

uint sample_presymptomatic_duration(global uint4* rng, global const Params* params){
  return (uint)rand_weibull(rng, params->presymp_scale, params->presymp_shape);
}

uint sample_infection_duration(global uint4* rng, global const Params* params){
  // FIXME: This is lognormal now
  float sample = randn(rng) * params->infection_scale + params->infection_loc;
  return sample * sign(sample); // Folded normal
}

float get_recovery_prob_for_age(ushort age, global const Params* params){
  uint bin_size = 10; // Years per bin
  uint max_bin_idx = 8; // Largest bin index covers 80+
  return params->recovery_probs[min(age/bin_size, max_bin_idx)];
}

/*
  Kernels
*/

// Reset the hazard and count of each place to zero.
kernel void places_reset(uint nplaces,
                         global uint* place_hazards,
                         global uint* place_counts) {
  int place_id = get_global_id(0);
  if (place_id >= nplaces) return;

  place_hazards[place_id] = 0;
  place_counts[place_id] = 0;
}

// Compute and set the movement flows for all the places for each person, 
// given the person's baseline movement flows (pre-calculated from activity specific flows and durations) and disease status.
// Includes lockdown logic.
kernel void people_update_flows(uint npeople,
                                uint nslots,
                                global const uint* people_statuses,
                                global const float* people_flows_baseline,
                                global float* people_flows,
                                global const uint* people_place_ids,
                                global const uint* place_activities,
                                global const struct Params* params) {
  int person_id = get_global_id(0);
  if (person_id >= npeople) return;

  uint person_status = people_statuses[person_id];

  // choose flow multiplier based on whether person is symptomatic or not
  // NB: lockdown is assumed not to change behaviour of symptomatic people, since it will already be reduced
  float non_home_multiplier = ((DiseaseStatus)person_status == Symptomatic) ? params->symptomatic_multiplier : params->lockdown_multiplier;
  
  float total_new_flow = 0.0;
  uint home_flow_idx = 0;
  
  // adjust non-home activity flows by the chosen multiplier, while summing the new flows so we can calculate the new home flow
  for(int slot = 0; slot < nslots; slot++){
    uint flow_idx = get_1d_index(person_id, slot, nslots);
    float baseline_flow = people_flows_baseline[flow_idx];
    uint place_id = people_place_ids[flow_idx];

    // check it is not an empty slot
    if (place_id != sentinel_value){
      uint activity = (Activity)place_activities[place_id];
      if (activity == Home) {
        // store flow index of home 
        home_flow_idx = flow_idx;
      } else { 
        // for non-home activities - adjust flow by multiplier
        float new_flow = baseline_flow * non_home_multiplier;
        people_flows[flow_idx] = new_flow;
        total_new_flow += new_flow;
      }
    }
  }

  // new home flow is 1 minus the total new flows for non-home activities, since all flows should sum to 1, 
  people_flows[home_flow_idx] = 1.0 - total_new_flow;
}

// Given their current status, accumulate hazard from each person into their candidate places.
kernel void people_send_hazards(uint npeople,
                                uint nslots,
                                global const uint* people_statuses,
                                global const uint* people_place_ids,
                                global const float* people_flows,
                                global const float* people_hazards,
                                volatile global uint* place_hazards,
                                volatile global uint* place_counts,
                                global const uint* place_activities,
                                global const Params* params) {
  int person_id = get_global_id(0);
  if (person_id >= npeople) return;

  // Early return for non infectious people
  DiseaseStatus person_status = (DiseaseStatus)people_statuses[person_id];
  if (!is_infectious(person_status)) return;

  for (int slot=0; slot < nslots; slot++) {
    // Get the place and flow for this slot
    uint flow_idx = get_1d_index(person_id, slot, nslots);
    uint place_id = people_place_ids[flow_idx];

    //check it is not an empty slot
    if (place_id == sentinel_value) continue;

    float flow = people_flows[flow_idx];
    uint activity = place_activities[place_id];
    //check it is a valid activity and select hazard multiplier
    flow *= (0 <= activity && activity <= 4) ? params->place_hazard_multipliers[activity] : 1.0;

    // Convert the flow to fixed point
    uint fixed_flow = (uint)(fixed_factor * flow);

    // Atomically increment hazards and counts for this place
    atomic_add(&place_hazards[place_id], fixed_flow);
    atomic_add(&place_counts[place_id], 1);
  }
}

//For each person accumulate hazard from all the places stored in their slots.
kernel void people_recv_hazards(uint npeople,
                                uint nslots,
                                global const uint* people_statuses,
                                global const uint* people_place_ids,
                                global const float* people_flows,
                                global float* people_hazards,
                                global const uint* place_hazards,
                                global const Params* params) {
  int person_id = get_global_id(0);
  if (person_id >= npeople) return;

  // Early return for non susceptible people
  DiseaseStatus person_status = (DiseaseStatus)people_statuses[person_id];
  if (person_status != Susceptible) return;

  // Initialize hazard to accumulate into
  float hazard = 0.0;

  for (int slot=0; slot < nslots; slot++) {
    // Get the place and flow for this slot
    uint flow_idx = get_1d_index(person_id, slot, nslots);
    uint place_id = people_place_ids[flow_idx];
    
    //check it is not an empty slot
    if (place_id == sentinel_value) continue;

    float flow = people_flows[flow_idx];

    // Get the hazard and convert it to floating point
    uint fixed_hazard = place_hazards[place_id];
    hazard += flow * (float)fixed_hazard / fixed_factor;
  }

  // Write the total hazard onto the individual
  people_hazards[person_id] = hazard;
}

// Disease model: given their current disease status and hazard, determine if a person is due to transition to the next
// state, and if so apply that transition.
kernel void people_update_statuses(uint npeople,
                                   global const ushort* people_ages,
                                   global const float* people_hazards,
                                   global uint* people_statuses,
                                   global uint* people_transition_times,
                                   global uint4* people_prngs,
                                   global const Params* params) {
  int person_id = get_global_id(0);
  if (person_id >= npeople) return;

  global uint4* rng = &people_prngs[person_id];

  DiseaseStatus current_status = (DiseaseStatus)people_statuses[person_id];
  DiseaseStatus next_status = current_status;

  uint current_transition_time = people_transition_times[person_id];
  uint next_transition_time = current_transition_time;

  // assign new infections to susceptible people 
  if (current_status == Susceptible){
    float hazard = people_hazards[person_id];
    // map hazard to probability between 0 and 1
    float infection_prob = hazard / (hazard + exp(-hazard));

    // randomly sample if they should be infected or not based on infection probability
    if (rand(rng) < infection_prob) {
      next_status = Exposed;
      next_transition_time = sample_exposed_duration(rng, params);
    }
  }

  // cycle through disease states
  if( current_transition_time <= 0 ) { // if time to transition to next state
    switch(current_status) {
        case Exposed:
        {
          next_status = Presymptomatic;
          next_transition_time = sample_presymptomatic_duration(rng, params);
          break;
        }
        case Presymptomatic:
        {
          // randomly select whether asymptomatic or not
          next_status = rand(rng) < params->proportion_asymptomatic ? Asymptomatic : Symptomatic;
          next_transition_time = sample_infection_duration(rng, params);
          break;
        }
        case Symptomatic:
        {
          // Calculate recovered prob based on age
          ushort person_age = people_ages[person_id];
          float recovery_prob = get_recovery_prob_for_age(person_age, params);
          
          // randomly select whether dead or recovered
          next_status = rand(rng) < recovery_prob ? Recovered : Dead;
          break;
        }
        case Asymptomatic:
        {
          next_status = Recovered; //assuming all asymptomatic infections recover
          break;
        }
        default:
          break;
    }
  }
  
  // decrement transition time each timestep
  if(next_transition_time > 0){
    next_transition_time--;
  }

  // apply new statuses and transition times
  people_statuses[person_id] = next_status;
  people_transition_times[person_id] = next_transition_time;
}