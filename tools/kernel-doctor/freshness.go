package main

import "time"

// Freshness reports whether a reviewed record is still inside its review
// window, and the note to print when it is not.
//
// The clock is a parameter, not time.Now() inside, so the boundary is a fixed
// test: the record is still fresh on the review-after date itself and turns
// overdue at 00:00 of the following day. A stale record must stay visible
// rather than quietly losing authority — the reviewed floors are only as good
// as the day they were read.
func Freshness(inc Incident, now time.Time) (bool, string) {
	after, err := time.Parse(time.DateOnly, inc.ReviewAfter)
	if err != nil {
		return false, "review-after date unreadable; policy_freshness=unknown"
	}
	if now.Before(after.AddDate(0, 0, 1)) {
		return true, ""
	}
	return false, "policy_freshness=overdue since " + inc.ReviewAfter
}
