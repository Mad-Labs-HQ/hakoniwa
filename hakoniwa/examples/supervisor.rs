//! Starts only as a supervisor whose host supplies the checked startup frame.
//!
//! The dependency fingerprint must match the host built in this consumer.

fn main() {
    hakoniwa::supervise();
}
