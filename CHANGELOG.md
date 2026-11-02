# Changelog

## [1.0.0]

### Changed

- Reworks difficulty aggregation to be exact: total work is accumulated as
  `fractions.Fraction` instead of floating-point estimates, and the scale-clamp
  that previously bounded the estimate is removed. (#2)
